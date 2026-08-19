import hashlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.deps import redis_service
from app.api.routes import admin, health, survey
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging_config import setup_logging
from app.middlewares.request_id import RequestIdMiddleware
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.database.session import engine

settings = get_settings()
# Logs em JSON fora de modo debug: formato esperado por agregadores de log
# em produção. Em desenvolvimento mantém o formato de uma linha legível.
setup_logging(json_logs=not settings.debug)
logger = logging.getLogger(__name__)

limiter.default_limits = [settings.rate_limit_default]

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Criados AQUI, no import, e não no lifespan: o app.mount() de /uploads lá
# embaixo também roda no import, e StaticFiles levanta
# "Directory '...' does not exist" já no construtor. Como o lifespan só roda
# depois, criar os diretórios lá dentro chegava tarde demais.
#
# Não é hipótese: o git versiona só `uploads/.gitkeep`, e UPLOAD_DIR aponta
# por padrão para `uploads/candidatos` — um subdiretório. Num clone novo a
# aplicação não subia, e a suíte inteira virava erro de conexão recusada
# (o servidor de teste morria antes de abrir a porta). Quem recebesse o
# repositório batia nisso no primeiro `docker compose up`.
#
# parents=True cobre UPLOAD_DIR apontando para caminho aninhado;
# exist_ok=True torna a chamada idempotente a cada import.
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


def _calcular_asset_version() -> str:
    """
    Impressão digital do CSS e do JS servidos, para entrar como `?v=` nos
    links dos templates.

    Sem isto, o navegador reaproveita o arquivo em cache e mistura HTML novo
    com script velho — que é bem pior do que só ficar com o visual antigo.
    O app.js anterior procurava `<select id="preferido">`; num HTML onde esse
    elemento não existe mais, a busca devolve null, o acesso estoura
    TypeError no topo do arquivo e NENHUM handler chega a ser registrado.
    A página carrega bonita e nenhum botão funciona. Foi exatamente assim
    que os botões novos de exportação do admin pareceram "não funcionar".

    Usa tamanho + mtime em vez do conteúdo: não precisa ler os arquivos, e
    qualquer edição muda pelo menos um dos dois. Calculado uma vez no import
    — dentro de um mesmo processo os estáticos não mudam, e no Docker a
    imagem é reconstruída a cada deploy de qualquer forma.
    """
    marcas = []
    for caminho in sorted((BASE_DIR / "static").rglob("*")):
        # uploads/ é conteúdo enviado pelo admin, não asset da aplicação:
        # incluir invalidaria o cache de todo mundo a cada foto nova.
        if caminho.is_file() and "uploads" not in caminho.parts:
            st = caminho.stat()
            marcas.append(f"{caminho.name}:{st.st_size}:{int(st.st_mtime)}")
    return hashlib.sha256("|".join(marcas).encode()).hexdigest()[:12]


ASSET_VERSION = _calcular_asset_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Aplicação iniciada: %s", settings.app_name)
    yield

    await redis_service.close()
    await engine.dispose()
    logger.info("Aplicação encerrada")


app = FastAPI(
    title=settings.app_name,
    description="Sondagem de intenção de votos para associados de clube",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
# Adicionado por último = executa primeiro (Starlette monta a pilha de
# middlewares na ordem inversa). O request id precisa existir antes de
# qualquer outro middleware logar, e o header X-Request-ID deve sair na
# resposta mesmo quando o rate limiter corta a requisição antes das rotas.
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount(
    "/uploads",
    StaticFiles(directory=str(Path(settings.upload_dir).resolve())),
    name="uploads",
)

app.include_router(health.router)
app.include_router(survey.router)
app.include_router(admin.router)


# A assinatura de TemplateResponse mudou no starlette: o request passou a
# ser o PRIMEIRO argumento posicional, e o contexto não o carrega mais
# dentro de si. Na forma antiga — TemplateResponse(nome, {"request": ...})
# — o starlette novo lê o nome do template como se fosse o request e o
# dicionário de contexto como se fosse o nome, e quebra com
# "TypeError: unhashable type: 'dict'" ao tentar usar o dict como chave de
# cache do Jinja.
@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recaptcha_site_key": settings.recaptcha_site_key,
            "app_name": settings.app_name,
            "asset_version": ASSET_VERSION,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"app_name": settings.app_name, "asset_version": ASSET_VERSION},
    )
