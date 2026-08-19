"""
De onde o rate limiter tira a chave de contagem.

O bug que estes testes travam: o limitador usava o `get_remote_address` do
slowapi, que lê só `request.client.host` e ignora `X-Forwarded-For`. Atrás
de um proxy reverso (nginx, Cloudflare, load balancer de cloud) isso faz
TODA requisição contar na mesma chave — a do proxy —, e cada limite "por
IP" vira um limite global do site inteiro. Com 30 cadastros/minuto, seriam
30 para todos os associados somados; o resto levaria 429.

O sintoma é traiçoeiro porque só aparece em produção: em desenvolvimento e
na suíte não há proxy, cada cliente chega com o próprio IP, e o limite se
comporta como esperado.

A direção contrária importa igual: confiar em `X-Forwarded-For` sem proxy
na frente é pior do que não confiar. Qualquer cliente manda o header à mão,
ganha uma chave nova a cada requisição e o rate limit deixa de existir.
"""

from unittest.mock import patch

import pytest
from starlette.datastructures import Headers

from app.core.limiter import chave_do_limitador


class _RequisicaoFalsa:
    """O mínimo de que a key_func precisa: .headers e .client.host."""

    class _Cliente:
        def __init__(self, host: str) -> None:
            self.host = host

    def __init__(self, host: str | None, headers: dict[str, str] | None = None) -> None:
        self.client = self._Cliente(host) if host else None
        self.headers = Headers(headers or {})


def _com_trust_proxy(valor: bool):
    """Troca só trust_proxy_headers, mantendo o resto das settings reais."""
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()

    class _Copia:
        def __getattr__(self, nome):
            if nome == "trust_proxy_headers":
                return valor
            return getattr(settings, nome)

    return patch("app.utils.client_ip.get_settings", return_value=_Copia())


class TestSemProxyConfiado:
    """TRUST_PROXY_HEADERS=false — o padrão."""

    def test_usa_o_ip_da_conexao(self):
        req = _RequisicaoFalsa("203.0.113.10")
        with _com_trust_proxy(False):
            assert chave_do_limitador(req) == "203.0.113.10"

    def test_ignora_x_forwarded_for_forjado(self):
        """Sem proxy declarado, o header é entrada de atacante. Se fosse
        aceito, bastaria variá-lo a cada requisição para nunca ser
        limitado."""
        req = _RequisicaoFalsa(
            "203.0.113.10", {"X-Forwarded-For": "1.2.3.4"}
        )
        with _com_trust_proxy(False):
            assert chave_do_limitador(req) == "203.0.113.10"


class TestAtrasDeProxy:
    """TRUST_PROXY_HEADERS=true — o cenário de produção."""

    def test_usa_o_ip_original_do_cliente(self):
        """Este é o conserto: sem ele a chave seria 10.0.0.1 (o proxy) para
        todo mundo, e o limite viraria global."""
        req = _RequisicaoFalsa("10.0.0.1", {"X-Forwarded-For": "203.0.113.10"})
        with _com_trust_proxy(True):
            assert chave_do_limitador(req) == "203.0.113.10"

    def test_pega_o_primeiro_da_cadeia(self):
        """Numa cadeia de proxies o cliente original é o primeiro; os
        seguintes são os saltos intermediários."""
        req = _RequisicaoFalsa(
            "10.0.0.1", {"X-Forwarded-For": "203.0.113.10, 70.41.3.18, 150.172.238.178"}
        )
        with _com_trust_proxy(True):
            assert chave_do_limitador(req) == "203.0.113.10"

    def test_clientes_distintos_nao_compartilham_chave(self):
        """A propriedade que o bug destruía: dois associados atrás do mesmo
        proxy precisam contar separado."""
        a = _RequisicaoFalsa("10.0.0.1", {"X-Forwarded-For": "203.0.113.10"})
        b = _RequisicaoFalsa("10.0.0.1", {"X-Forwarded-For": "198.51.100.7"})
        with _com_trust_proxy(True):
            assert chave_do_limitador(a) != chave_do_limitador(b)

    def test_sem_o_header_cai_no_ip_da_conexao(self):
        """Proxy configurado mas requisição sem o header (health check local,
        por exemplo): não pode devolver None, que quebraria a key_func."""
        req = _RequisicaoFalsa("10.0.0.1")
        with _com_trust_proxy(True):
            assert chave_do_limitador(req) == "10.0.0.1"


class TestNuncaDevolveNone:
    def test_sem_cliente_e_sem_header_ainda_devolve_string(self):
        """A key_func do slowapi precisa de str. Transporte ASGI de teste
        pode não ter request.client; devolver None estouraria a requisição
        inteira em vez de só limitar."""
        req = _RequisicaoFalsa(None)
        with _com_trust_proxy(False):
            chave = chave_do_limitador(req)
        assert isinstance(chave, str) and chave


class TestLimitesSobrevivemAoNatDeOperadora:
    """
    Item 2 do diagnóstico de capacidade: o link circula em grupo de
    WhatsApp, todo mundo abre pelo celular, e operadoras colocam muitos
    assinantes atrás do mesmo IP público (CGNAT). Com 10 cadastros/minuto,
    o 11º sócio da mesma operadora levava 429 sem ter feito nada errado.

    O número exato é ajustável por ambiente; o piso abaixo existe para que
    ninguém volte aos valores de "um IP = uma pessoa" sem perceber que essa
    premissa não vale aqui. Quem apertar de propósito (divulgação por canal
    fechado) muda a variável de ambiente, não o default.
    """

    @pytest.mark.parametrize(
        "atributo,minimo",
        [
            ("rate_limit_register", 30),
            ("rate_limit_verify_otp", 30),
            ("rate_limit_submit", 30),
            ("rate_limit_validate_cpf", 60),
            ("rate_limit_default", 120),
        ],
    )
    def test_limite_publico_tem_folga_para_ip_compartilhado(self, atributo, minimo):
        from app.core.config import Settings

        # O default da classe, não o valor do ambiente: o conftest aperta
        # alguns limites de propósito para os testes de 429 rodarem rápido.
        configurado = Settings.model_fields[atributo].default
        quantidade = int(configurado.partition("/")[0].strip())

        assert quantidade >= minimo, (
            f"{atributo} tem default {configurado}, abaixo do piso de "
            f"{minimo}/minuto. Atrás de CGNAT isso bloqueia sócios "
            f"legítimos entre si — ver o comentário em app/core/config.py."
        )
