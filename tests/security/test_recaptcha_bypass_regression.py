from types import SimpleNamespace

import pytest

from app.integrations.recaptcha import RecaptchaService


class TestRecaptchaBypassRemoved:
    """
    Regressão do achado C2 da auditoria: app/integrations/recaptcha.py tinha
    `return self.settings.debug or token == "dev-bypass"` quando a chave não
    estava configurada — qualquer um lendo o repositório público (é open
    source) descobria esse token mágico e passava pela verificação mesmo
    com DEBUG=false. Corrigido: sem chave configurada, só passa com
    DEBUG=true; fora disso, falha fechado sempre, não importa o token.

    Testado diretamente no serviço (não via HTTP) com settings simulados,
    para não depender de subir um segundo servidor só com DEBUG=false.
    """

    def _service_with(self, *, debug: bool, secret_key: str = "") -> RecaptchaService:
        service = RecaptchaService()
        service.settings = SimpleNamespace(
            debug=debug, recaptcha_secret_key=secret_key, recaptcha_min_score=0.5
        )
        return service

    @pytest.mark.parametrize("token", ["dev-bypass", "qualquer-outra-string", "", "null"])
    async def test_dev_bypass_string_rejected_outside_debug(self, token):
        service = self._service_with(debug=False)
        assert await service.verify(token) is False

    async def test_debug_mode_bypasses_regardless_of_token(self):
        service = self._service_with(debug=True)
        assert await service.verify("qualquer-token-mesmo-invalido") is True
        assert await service.verify("dev-bypass") is True
