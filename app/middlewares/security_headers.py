from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

# CSP restritiva: só permite recursos do próprio domínio, além dos hosts
# explicitamente usados pelo app — jsDelivr (Bootstrap, carregado pelos
# templates) e o script do Google reCAPTCHA. Ajustar aqui se novos
# scripts/estilos externos forem adicionados. O README já afirmava que
# isso existia; esta é a implementação real que faltava.
#
# Nem script-src nem style-src têm 'unsafe-inline'. Manter assim:
#
# - Em script-src, 'unsafe-inline' reabriria o XSS armazenado (achado C1)
#   mesmo com a sanitização no service — bastaria um ponto de escape para
#   o payload voltar a executar. É por isso que o admin.js usa event
#   delegation em vez de onclick= no HTML gerado.
#
# - Em style-src, saiu quando os style="" dos templates viraram classes
#   (.flow-shell no fluxo público, .login-card no admin). Sem ele, um
#   atacante que consiga injetar
#   HTML não consegue mais usar CSS para atacar: nem sobrepor a página
#   inteira com um formulário falso, nem exfiltrar conteúdo por seletor de
#   atributo + background-image.
#
# O fluxo público não usa element.style em lugar nenhum: o progresso das
# etapas são as bolinhas do cabeçalho, e o app.js muda o estado delas por
# classList (is-done / is-current). A barra de progresso anterior escapava
# da CSP por outro motivo — element.style.width é CSSOM, e 'unsafe-inline'
# governa só o atributo style= vindo do HTML. Trocar por classe removeu a
# dependência dessa distinção.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://www.google.com https://www.gstatic.com; "
    "frame-src https://www.google.com; "
    "style-src 'self' https://cdn.jsdelivr.net; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        settings = get_settings()

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = _CSP

        # Respostas da API admin podem conter dados de associados (CPF,
        # telefone) — nunca devem ficar em cache do navegador/proxy.
        if request.url.path.startswith("/api/admin"):
            response.headers["Cache-Control"] = "no-store"

        if settings.https_only:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
