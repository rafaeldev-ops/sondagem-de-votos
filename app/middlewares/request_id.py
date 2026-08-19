import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import request_id_var

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Atribui um ID único a cada requisição, propaga para todos os logs
    emitidos durante o processamento dela (via ContextVar) e devolve no
    header X-Request-ID.

    Se o cliente (ou um proxy reverso na frente) já enviar um X-Request-ID,
    reaproveitamos esse valor em vez de gerar outro — assim o mesmo id
    percorre toda a cadeia e dá para correlacionar um erro reportado pelo
    usuário com as linhas de log correspondentes.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming if incoming else uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "Erro não tratado em %s %s (%.1fms)",
                request.method,
                request.url.path,
                duration_ms,
            )
            request_id_var.reset(token)
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id

        # Log de acesso estruturado: método, rota, status e latência. Não
        # loga query string nem corpo — podem conter CPF/telefone.
        # O reset do ContextVar acontece DEPOIS desta linha de propósito:
        # resetar antes fazia todo log de acesso sair com request_id "-",
        # anulando a correlação que este middleware existe para fornecer.
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        request_id_var.reset(token)
        return response
