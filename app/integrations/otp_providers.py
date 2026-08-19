import logging
from abc import ABC, abstractmethod

import httpx
from twilio.rest import Client

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OTPProvider(ABC):
    @abstractmethod
    async def send_otp(self, phone: str, code: str) -> bool:
        pass


class MockOTPProvider(OTPProvider):
    """
    Provider de desenvolvimento: não envia SMS/WhatsApp de verdade, só
    escreve o código no log da aplicação para dar para testar o fluxo
    localmente sem contratar provedor.

    Loga o código em texto puro POR DESIGN — é essa a utilidade dele. Por
    isso recusa funcionar fora de DEBUG=true: se alguém subir para produção
    com OTP_PROVIDER=mock por engano, todos os códigos ativos iriam parar
    no log da aplicação (e nenhum SMS real sairia). Melhor falhar alto na
    primeira tentativa de envio do que descobrir isso depois.
    """

    async def send_otp(self, phone: str, code: str) -> bool:
        settings = get_settings()
        if not settings.debug:
            logger.error(
                "OTP_PROVIDER=mock fora de modo debug — recusando enviar. "
                "Configure um provedor real (twilio/zenvia/zapi) em produção."
            )
            return False
        logger.info("OTP mock enviado para %s: %s", phone, code)
        return True


class TwilioOTPProvider(OTPProvider):
    async def send_otp(self, phone: str, code: str) -> bool:
        settings = get_settings()
        try:
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            message = client.messages.create(
                body=f"Código de verificação para a Sondagem: {code}",
                from_=settings.twilio_from_number,
                to=f"+55{phone}",
            )
            logger.info("Twilio OTP enviado: %s", message.sid)
            return True
        except Exception as exc:
            logger.exception("Erro ao enviar OTP via Twilio: %s", exc)
            return False


class ZenviaOTPProvider(OTPProvider):
    async def send_otp(self, phone: str, code: str) -> bool:
        settings = get_settings()
        url = "https://api.zenvia.com/v2/channels/sms/messages"
        headers = {
            "X-API-TOKEN": settings.zenvia_api_token,
            "Content-Type": "application/json",
        }
        payload = {
            "from": settings.zenvia_from,
            "to": f"55{phone}",
            "contents": [
                {
                    "type": "text",
                    "text": f"Código de verificação para a Sondagem: {code}",
                }
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.exception("Erro ao enviar OTP via Zenvia: %s", exc)
            return False


class ZAPIOTPProvider(OTPProvider):
    async def send_otp(self, phone: str, code: str) -> bool:
        settings = get_settings()
        url = (
            f"https://api.z-api.io/instances/{settings.zapi_instance_id}"
            f"/token/{settings.zapi_token}/send-text"
        )
        headers = {"Client-Token": settings.zapi_client_token}
        payload = {
            "phone": f"55{phone}",
            "message": f"Código de verificação para a Sondagem: {code}",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.exception("Erro ao enviar OTP via Z-API: %s", exc)
            return False


class VonageOTPProvider(OTPProvider):
    """
    Ao contrário dos outros providers daqui, o status HTTP não basta: a Vonage
    responde 200 mesmo quando não envia a mensagem, e o resultado real vem no
    corpo, em `messages[0].status` ("0" = enviado, qualquer outro valor é
    recusa). Sem ler o corpo, uma conta sem crédito — ou o sender alfanumérico
    recusado pela operadora brasileira — seria registrada como envio bem
    sucedido, e o associado ficaria esperando um SMS que nunca saiu.
    """

    async def send_otp(self, phone: str, code: str) -> bool:
        settings = get_settings()
        url = "https://rest.nexmo.com/sms/json"
        payload = {
            "api_key": settings.vonage_api_key,
            "api_secret": settings.vonage_api_secret,
            "to": f"55{phone}",
            "from": settings.vonage_from,
            "text": f"Código de verificação para a Sondagem: {code}",
            # Sem isto a Vonage manda em GSM-7, que não tem "ó", "çã" nem "á"
            # no alfabeto básico — cada um vira "?" na tela do associado
            # ("c?digo", "verifica??o", "V?lido"). A mensagem tem ~60
            # caracteres, dentro do limite de 70 de um único segmento em
            # UCS-2, então não parte em duas mensagens.
            "type": "unicode",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, data=payload)
                response.raise_for_status()
                corpo = response.json()
        except Exception as exc:
            logger.exception("Erro ao enviar OTP via Vonage: %s", exc)
            return False

        try:
            mensagem = corpo["messages"][0]
            status = mensagem["status"]
        except (KeyError, IndexError, TypeError):
            logger.error("Resposta da Vonage em formato inesperado: %s", corpo)
            return False

        if status != "0":
            logger.error(
                "Vonage recusou o envio para %s: status=%s (%s)",
                phone,
                status,
                mensagem.get("error-text", "sem detalhe"),
            )
            return False

        logger.info("Vonage OTP enviado para %s", phone)
        return True


def get_otp_provider() -> OTPProvider:
    settings = get_settings()
    providers: dict[str, OTPProvider] = {
        "twilio": TwilioOTPProvider(),
        "zenvia": ZenviaOTPProvider(),
        "zapi": ZAPIOTPProvider(),
        "vonage": VonageOTPProvider(),
        "mock": MockOTPProvider(),
    }
    return providers.get(settings.otp_provider, MockOTPProvider())
