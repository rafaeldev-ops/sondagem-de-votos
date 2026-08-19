"""
Regressão: a API da Vonage responde HTTP 200 mesmo quando a mensagem não é
enviada. O resultado real vem no corpo, em `messages[0].status`, onde "0" é
sucesso e qualquer outro valor é falha ("2" = parâmetro faltando, "9" = quota
estourada, "15" = sender recusado para o destino — o caso mais provável aqui,
porque `VONAGE_FROM` é alfanumérico e as operadoras brasileiras não entregam
sender alfanumérico).

O provider olhava só o status HTTP, então uma conta sem crédito era reportada
como envio bem-sucedido: o associado via "código enviado para seu celular",
nenhum SMS chegava, e o log da aplicação dizia que tinha dado certo. Fica
impossível distinguir "não chegou por causa da operadora" de "a Vonage
recusou", que é justamente o que se precisa saber ao ligar o provedor de
verdade pela primeira vez.
"""

import json

import pytest

import app.integrations.otp_providers as otp_providers
from app.integrations.otp_providers import VonageOTPProvider


class _RespostaFake:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _ClienteFake:
    """
    Entra no lugar de `httpx.AsyncClient`: serve como a própria classe (é
    chamado com os kwargs do construtor) e como o cliente devolvido pelo
    `async with`. Nenhuma requisição sai da máquina.
    """

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.chamadas: list[tuple[str, dict]] = []

    def __call__(self, *args, **kwargs) -> "_ClienteFake":
        return self

    async def __aenter__(self) -> "_ClienteFake":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(self, url: str, data: dict | None = None, **kwargs) -> _RespostaFake:
        self.chamadas.append((url, data or {}))
        return _RespostaFake(self._payload)


@pytest.fixture
def responder_vonage(monkeypatch):
    def _instalar(payload: dict) -> _ClienteFake:
        cliente = _ClienteFake(payload)
        monkeypatch.setattr(otp_providers.httpx, "AsyncClient", cliente)
        return cliente

    return _instalar


class TestVonageLeStatusDoCorpo:
    async def test_falha_no_corpo_com_http_200_nao_conta_como_envio(self, responder_vonage):
        responder_vonage(
            {
                "message-count": "1",
                "messages": [
                    {
                        "status": "15",
                        "error-text": "Illegal Sender Address - rejected",
                        "to": "5511999998888",
                    }
                ],
            }
        )

        assert await VonageOTPProvider().send_otp("11999998888", "123456") is False

    async def test_status_zero_conta_como_envio(self, responder_vonage):
        cliente = responder_vonage(
            {
                "message-count": "1",
                "messages": [
                    {"status": "0", "message-id": "0A0000000123ABCD1", "to": "5511999998888"}
                ],
            }
        )

        assert await VonageOTPProvider().send_otp("11999998888", "123456") is True
        assert cliente.chamadas, "o provider precisa ter chamado a API"

    async def test_corpo_em_formato_inesperado_nao_conta_como_envio(self, responder_vonage):
        responder_vonage({"error": "manutenção"})

        assert await VonageOTPProvider().send_otp("11999998888", "123456") is False

    async def test_falha_no_corpo_registra_o_motivo_no_log(self, responder_vonage, caplog):
        responder_vonage(
            {"messages": [{"status": "9", "error-text": "Partner quota exceeded"}]}
        )

        await VonageOTPProvider().send_otp("11999998888", "123456")

        assert "Partner quota exceeded" in caplog.text
        assert "9" in caplog.text

    async def test_codigo_nao_vai_para_o_log_no_caminho_de_sucesso(self, responder_vonage, caplog):
        """
        O provider real loga o envio; o código é o segredo do OTP e não pode
        vazar para o log como acontece de propósito no MockOTPProvider.
        """
        responder_vonage({"messages": [{"status": "0", "message-id": "abc"}]})

        await VonageOTPProvider().send_otp("11999998888", "123456")

        assert "123456" not in caplog.text
