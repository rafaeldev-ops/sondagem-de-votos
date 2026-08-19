
import secrets

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import (
    ADMIN_CSRF_COOKIE,
    ADMIN_TOKEN_COOKIE,
    CSRF_HEADER,
    decode_access_token,
)
from app.database.session import get_db  # noqa: F401 — re-exported for route imports
from app.services.otp_service import OTPService, RedisService
from app.utils.client_ip import extrair_ip_do_cliente

# Métodos que alteram estado e por isso precisam passar pela checagem de
# CSRF. GET/HEAD/OPTIONS ficam de fora porque não deveriam ter efeito
# colateral — as rotas de exportação são GET e só leem dados.
_METODOS_INSEGUROS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

redis_service = RedisService()


def get_redis_service() -> RedisService:
    return redis_service


def get_otp_service(redis_svc: RedisService = Depends(get_redis_service)) -> OTPService:
    return OTPService(redis_svc)


async def get_client_ip(request: Request) -> str | None:
    """
    IP do cliente para o audit log, como dependência do FastAPI.

    A lógica mora em app/utils/client_ip.py porque o rate limiter precisa
    dela também, e a key_func do slowapi é síncrona — não dá para reusar
    esta função async. Enquanto as duas eram implementações separadas, o
    limitador ficou para trás e ignorava X-Forwarded-For.
    """
    return extrair_ip_do_cliente(request)


def get_user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent")


def validate_csrf(request: Request) -> None:
    """
    Double submit cookie: o valor do cookie ADMIN_CSRF_COOKIE precisa bater
    com o header X-CSRF-Token.

    Por que isso protege: um site atacante consegue *disparar* uma
    requisição para cá e o navegador anexa o cookie de sessão sozinho — é
    o CSRF clássico. O que ele não consegue é **ler** o cookie de CSRF (a
    same-origin policy bloqueia a leitura entre origens diferentes) nem
    mandar um header customizado sem passar por um preflight de CORS que
    só aprovamos para as origens em ALLOWED_ORIGINS. Sem o valor do
    cookie, ele não tem como preencher o header.

    Isso é redundante com o SameSite=Strict do cookie, e de propósito. O
    SameSite sozinho já barraria o ataque em qualquer navegador atual,
    mas ele é uma diretiva que o navegador escolhe respeitar: um
    navegador antigo que a ignore, ou uma extensão/proxy que reescreva o
    cookie, derrubam a única defesa. Este painel exporta CPF e telefone de
    associados — vale a segunda camada.
    """
    if request.method not in _METODOS_INSEGUROS:
        return

    cookie_csrf = request.cookies.get(ADMIN_CSRF_COOKIE)
    header_csrf = request.headers.get(CSRF_HEADER)

    # compare_digest em vez de == para não vazar quanto do valor bateu
    # pelo tempo da comparação.
    if not cookie_csrf or not header_csrf or not secrets.compare_digest(cookie_csrf, header_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF ausente ou inválido",
        )


async def get_admin_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Autentica o admin pelo cookie httpOnly, com o header Authorization
    ainda aceito como alternativa.

    Os dois caminhos coexistem de propósito. O cookie é o que o painel usa
    (o JWT saiu do localStorage, onde um XSS o lia direto). O bearer
    continua valendo para chamadas fora do navegador — scripts, curl, o
    job de verificação do CI — que não têm cookie jar e para as quais CSRF
    não faz sentido: nenhum navegador anexa um header Authorization
    sozinho numa requisição cross-site, que é justamente o que torna o
    CSRF possível com cookie.

    Por isso a checagem de CSRF só roda quando a autenticação veio do
    cookie. Um bearer válido não ganha nada em pular a checagem: quem tem
    o token já está autenticado de qualquer forma.
    """
    cookie_token = request.cookies.get(ADMIN_TOKEN_COOKIE)

    if cookie_token:
        token = cookie_token
        veio_do_cookie = True
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        veio_do_cookie = False
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação necessário",
        )

    payload = decode_access_token(token)
    if not payload or payload.get("sub") != get_settings().admin_username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )

    if veio_do_cookie:
        validate_csrf(request)

    return payload
