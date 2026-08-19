import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import get_redis_service
from app.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict:
    """Liveness: só confirma que o processo está de pé. Não verifica
    dependências de propósito — usado pelo HEALTHCHECK do Docker/orquestrador
    para decidir se reinicia o container; misturar isso com checagem de DB/
    Redis faria uma instabilidade passageira no banco derrubar o container
    inteiro à toa, mesmo com o processo saudável."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_check(response: Response) -> dict:
    """Readiness: verifica de verdade se a aplicação consegue falar com
    Postgres e Redis — para uso por load balancer/orquestrador na hora de
    decidir se deve rotear tráfego para esta instância."""
    checks = {"database": False, "redis": False}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        logger.warning("Readiness check: banco indisponível: %s", exc)

    try:
        redis_client = await get_redis_service().get_client()
        await redis_client.ping()
        checks["redis"] = True
    except Exception as exc:
        logger.warning("Readiness check: redis indisponível: %s", exc)

    ready = all(checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if ready else "not ready", "checks": checks}
