import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RecaptchaService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def verify(self, token: str, remote_ip: str | None = None) -> bool:
        if not self.settings.recaptcha_secret_key:
            if self.settings.debug:
                logger.warning(
                    "reCAPTCHA não configurado — permitindo por estar em DEBUG=true. "
                    "Isso NUNCA deve ficar ativo em produção."
                )
                return True
            # Produção sem chave configurada: falha fechado. Antes deste fix,
            # havia um token mágico "dev-bypass" hardcoded que qualquer pessoa
            # lendo o repositório público podia usar para passar por aqui
            # mesmo com DEBUG=false. Isso foi removido — sem chave configurada
            # e fora de modo debug, a verificação sempre falha.
            logger.error(
                "reCAPTCHA sem RECAPTCHA_SECRET_KEY configurada fora de modo debug — "
                "recusando por segurança."
            )
            return False

        data = {
            "secret": self.settings.recaptcha_secret_key,
            "response": token,
        }
        if remote_ip:
            data["remoteip"] = remote_ip

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://www.google.com/recaptcha/api/siteverify",
                    data=data,
                )
                result = response.json()

            if not result.get("success"):
                logger.warning("reCAPTCHA falhou: %s", result.get("error-codes"))
                return False

            score = result.get("score", 0)
            return score >= self.settings.recaptcha_min_score
        except Exception as exc:
            logger.exception("Erro ao verificar reCAPTCHA: %s", exc)
            return False
