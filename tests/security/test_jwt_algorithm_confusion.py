"""
Confusão de algoritmo no JWT do admin.

Motivo de existir: a troca de python-jose por PyJWT mexeu na validação de
token do admin — o ponto onde um erro vira "qualquer um entra no painel".
Os testes de tests/unit/test_security.py cobrem o caminho feliz e o token
adulterado, mas nenhum deles afirmava que a validação está presa a HS256.

Uma implementação que confia no `alg` declarado no header do próprio token
aceita `{"alg": "none"}` sem assinatura nenhuma. É a falha clássica de
JWT, e ela não aparece em nenhum teste de roundtrip: o caminho feliz
continua funcionando perfeitamente enquanto o bypass está aberto.
"""

import base64
import json

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.core.security import ALGORITHM, create_access_token, decode_access_token

# Os testes abaixo assinam de propósito com chaves curtas / algoritmo
# errado para produzir tokens que devem ser recusados. O aviso do PyJWT
# sobre comprimento de chave é esperado aqui e só polui a saída — a chave
# de produção vem de `secrets.token_urlsafe(64)`, bem acima do mínimo.
_ignora_aviso_de_chave_curta = pytest.mark.filterwarnings(
    "ignore::jwt.warnings.InsecureKeyLengthWarning"
)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _forjar(header: dict, payload: dict, assinatura: str = "") -> str:
    """Monta um JWT à mão, sem passar por nenhuma biblioteca."""
    h = _b64(json.dumps(header).encode())
    p = _b64(json.dumps(payload).encode())
    return f"{h}.{p}.{assinatura}"


class TestAlgorithmConfusion:
    def test_algoritmo_none_rejeitado(self):
        """Token sem assinatura, declarando alg=none no header."""
        token = _forjar({"alg": "none", "typ": "JWT"}, {"sub": "admin", "exp": 9999999999})
        assert decode_access_token(token) is None

    def test_algoritmo_none_maiusculo_rejeitado(self):
        """Variação de caixa é uma forma conhecida de driblar comparação ingênua."""
        token = _forjar({"alg": "NONE", "typ": "JWT"}, {"sub": "admin", "exp": 9999999999})
        assert decode_access_token(token) is None

    @_ignora_aviso_de_chave_curta
    def test_outro_algoritmo_hmac_rejeitado(self):
        """
        Assinado com a chave correta, mas em HS512 em vez de HS256. Só é
        recusado porque decode_access_token passa algorithms=[HS256]
        explicitamente em vez de aceitar o que vier no header.
        """
        token = pyjwt.encode(
            {"sub": "admin", "exp": 9999999999},
            get_settings().secret_key,
            algorithm="HS512",
        )
        assert decode_access_token(token) is None

    @_ignora_aviso_de_chave_curta
    def test_assinatura_com_outro_segredo_rejeitada(self):
        token = pyjwt.encode(
            {"sub": "admin", "exp": 9999999999},
            "outro-segredo-qualquer",
            algorithm=ALGORITHM,
        )
        assert decode_access_token(token) is None

    def test_payload_alterado_invalida_a_assinatura(self):
        """Trocar o sub sem reassinar não pode passar."""
        valido = create_access_token({"sub": "admin"})
        header, _, assinatura = valido.split(".")
        payload_falso = _b64(json.dumps({"sub": "invasor", "exp": 9999999999}).encode())

        assert decode_access_token(f"{header}.{payload_falso}.{assinatura}") is None

    def test_token_sem_assinatura_rejeitado(self):
        valido = create_access_token({"sub": "admin"})
        header, payload, _ = valido.split(".")

        assert decode_access_token(f"{header}.{payload}.") is None


class TestBibliotecaJwt:
    def test_python_jose_nao_esta_mais_no_ambiente(self):
        """
        python-jose saiu para eliminar ecdsa e pyasn1 (5 CVEs sem correção
        possível enquanto ele exigia pyasn1<0.5.0). Se alguém reinstalar a
        lib, as CVEs voltam junto — este teste avisa.
        """
        import importlib.util

        assert importlib.util.find_spec("jose") is None, (
            "python-jose voltou ao ambiente — traz ecdsa e pyasn1 junto"
        )
