import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime

import redis.asyncio as redis

from app.core.config import get_settings
from app.integrations.otp_providers import get_otp_provider
from app.utils.otp_generator import generate_otp

logger = logging.getLogger(__name__)


def _hash_code(code: str) -> str:
    """
    Hash do código OTP antes de qualquer persistência. O Redis nunca guarda
    o código em texto puro — quem tiver acesso de leitura ao Redis (backup,
    réplica, ferramenta de monitoramento, ou uma porta exposta por engano)
    não consegue extrair o código válido a partir do que está armazenado.
    """
    return hashlib.sha256(code.encode()).hexdigest()


# Script Lua: roda de forma atômica dentro do Redis (single-threaded),
# eliminando a race condition do padrão anterior (GET em Python, modifica
# em Python, SETEX de volta) onde duas verificações concorrentes podiam ler
# o mesmo "tentativas" antes de qualquer uma escrever de volta.
#
# A comparação do hash usa constant_time_eq em vez de == direto: Lua não
# tem hmac.compare_digest, mas o `==` de string do Lua normalmente retorna
# assim que encontra o primeiro byte diferente, vazando timing sobre em
# qual posição os hashes divergem. Como isso roda dentro do Redis (não dá
# pra mover pro Python sem reabrir a race condition do contador de
# tentativas que este script resolve), a comparação de tempo constante
# precisa ser implementada aqui mesmo.
_VERIFY_OTP_SCRIPT = """
local function constant_time_eq(a, b)
    if #a ~= #b then
        return false
    end
    local diff = 0
    for i = 1, #a do
        if string.byte(a, i) ~= string.byte(b, i) then
            diff = diff + 1
        end
    end
    return diff == 0
end

local raw = redis.call('GET', KEYS[1])
if not raw then
    return {0, 'expired'}
end

local data = cjson.decode(raw)
local max_attempts = tonumber(ARGV[2])

if data.tentativas >= max_attempts then
    redis.call('DEL', KEYS[1])
    return {0, 'max_attempts', data.tentativas}
end

if constant_time_eq(data.codigo_hash, ARGV[1]) then
    redis.call('DEL', KEYS[1])
    return {1, 'ok'}
end

data.tentativas = data.tentativas + 1
local ttl = redis.call('TTL', KEYS[1])
if ttl > 0 then
    redis.call('SETEX', KEYS[1], ttl, cjson.encode(data))
else
    redis.call('DEL', KEYS[1])
end
return {0, 'invalid', data.tentativas}
"""


class RedisService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: redis.Redis | None = None
        self._verify_otp_sha: str | None = None

    async def get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                self.settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def get_verify_otp_script(self) -> str:
        """Carrega (e cacheia) o SHA do script Lua de verificação de OTP."""
        client = await self.get_client()
        if self._verify_otp_sha is None:
            self._verify_otp_sha = await client.script_load(_VERIFY_OTP_SCRIPT)
        return self._verify_otp_sha

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()


class OTPService:
    OTP_PREFIX = "otp:"
    RESEND_PREFIX = "otp_resend:"
    SESSION_PREFIX = "session:"

    def __init__(self, redis_service: RedisService) -> None:
        self.redis_service = redis_service
        self.settings = get_settings()
        self.provider = get_otp_provider()

    def _otp_key(self, phone: str) -> str:
        return f"{self.OTP_PREFIX}{phone}"

    def _resend_key(self, phone: str) -> str:
        return f"{self.RESEND_PREFIX}{phone}"

    def _session_key(self, token: str) -> str:
        return f"{self.SESSION_PREFIX}{token}"

    async def create_session(self, data: dict) -> str:
        client = await self.redis_service.get_client()
        token = secrets.token_urlsafe(32)
        key = self._session_key(token)
        await client.setex(key, self.settings.otp_expiry_seconds * 4, json.dumps(data))
        return token

    async def get_session(self, token: str) -> dict | None:
        client = await self.redis_service.get_client()
        data = await client.get(self._session_key(token))
        if not data:
            return None
        return json.loads(data)

    async def update_session(self, token: str, data: dict, ttl: int | None = None) -> None:
        client = await self.redis_service.get_client()
        ttl = ttl or self.settings.otp_expiry_seconds * 4
        await client.setex(self._session_key(token), ttl, json.dumps(data))

    async def delete_session(self, token: str) -> None:
        client = await self.redis_service.get_client()
        await client.delete(self._session_key(token))

    async def send_otp(self, phone: str) -> tuple[bool, str | None]:
        client = await self.redis_service.get_client()

        resend_key = self._resend_key(phone)
        if await client.exists(resend_key):
            ttl = await client.ttl(resend_key)
            return False, f"Aguarde {ttl} segundos para reenviar"

        code = generate_otp()
        otp_data = {
            # Nunca gravar o código em texto puro — só o hash. O código em
            # claro só existe em memória neste processo, pelo tempo
            # necessário para chamar o provedor de envio (SMS/WhatsApp).
            "codigo_hash": _hash_code(code),
            "tentativas": 0,
            "criado_em": datetime.now(UTC).isoformat(),
        }

        otp_key = self._otp_key(phone)
        await client.setex(
            otp_key,
            self.settings.otp_expiry_seconds,
            json.dumps(otp_data),
        )
        # Cooldown 0 = desabilitado (útil em teste de carga/homologação).
        # Não dá para gravar isso como SETEX: o Redis recusa TTL 0 com
        # "invalid expire time in 'setex' command", o que fazia toda
        # chamada a /register devolver 500. Simplesmente não gravar a
        # chave já expressa "sem cooldown" — a checagem lá em cima é um
        # EXISTS, que dá falso quando a chave não existe.
        if self.settings.otp_resend_cooldown_seconds > 0:
            await client.setex(
                resend_key,
                self.settings.otp_resend_cooldown_seconds,
                "1",
            )

        success = await self.provider.send_otp(phone, code)
        if not success:
            await client.delete(otp_key)
            return False, "Falha ao enviar código OTP"

        return True, None

    async def verify_otp(self, phone: str, code: str) -> tuple[bool, str | None]:
        client = await self.redis_service.get_client()
        otp_key = self._otp_key(phone)
        code_hash = _hash_code(code)
        script_sha = await self.redis_service.get_verify_otp_script()

        try:
            result = await client.evalsha(
                script_sha, 1, otp_key, code_hash, self.settings.otp_max_attempts
            )
        except redis.ResponseError as exc:
            # NOSCRIPT: o script pode ter sido evictado do cache do Redis
            # (ex: após um FLUSHALL ou reinício). Recarrega e tenta de novo.
            if "NOSCRIPT" in str(exc):
                self.redis_service._verify_otp_sha = None
                script_sha = await self.redis_service.get_verify_otp_script()
                result = await client.evalsha(
                    script_sha, 1, otp_key, code_hash, self.settings.otp_max_attempts
                )
            else:
                raise

        status = result[1]

        if status == "expired":
            return False, "Código expirado. Solicite um novo código."
        if status == "max_attempts":
            return False, "Número máximo de tentativas excedido. Solicite um novo código."
        if status == "ok":
            return True, None

        # status == "invalid"
        remaining = self.settings.otp_max_attempts - result[2]
        return False, f"Código inválido. Restam {remaining} tentativa(s)."
