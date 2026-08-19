import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_token, get_db
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.security import (
    ADMIN_CSRF_COOKIE,
    ADMIN_TOKEN_COOKIE,
    create_access_token,
    generate_csrf_token,
    verify_password,
)
from app.schemas import AdminLoginRequest, AdminTokenResponse, StatsResponse
from app.services.admin_service import AdminService
from app.services.survey_service import ExportService
from app.utils.datetime_br import format_datetime_br

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Lido no import pelo mesmo motivo de app/api/routes/survey.py: o decorator
# @limiter.limit(...) é avaliado quando o módulo carrega, então precisa de
# um objeto de settings já disponível aqui (get_settings é cacheado com
# lru_cache).
_settings = get_settings()


@router.post("/login", response_model=AdminTokenResponse)
@limiter.limit(_settings.rate_limit_admin_login)
async def admin_login(
    request: Request, response: Response, body: AdminLoginRequest
) -> AdminTokenResponse:
    settings = get_settings()
    if body.username != settings.admin_username:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    stored = settings.admin_password
    valid = (
        verify_password(body.password, stored)
        if stored.startswith("$2")
        else body.password == stored
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = create_access_token(
        {"sub": settings.admin_username},
        expires_delta=timedelta(minutes=settings.admin_jwt_expire_minutes),
    )
    csrf_token = generate_csrf_token()
    max_age = settings.admin_jwt_expire_minutes * 60

    # Secure acompanha HTTPS_ONLY em vez de ser fixo: com Secure=True o
    # navegador descarta o cookie em http://, o que quebraria o painel em
    # desenvolvimento local. Em produção HTTPS_ONLY=true é obrigatório —
    # a aplicação trata CPF e telefone (ver docs/PRODUCAO.md, seção 2).
    secure = settings.https_only

    response.set_cookie(
        ADMIN_TOKEN_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    # Este NÃO é httpOnly de propósito: o admin.js precisa ler o valor
    # para reenviá-lo no header X-CSRF-Token. Não é credencial — sozinho
    # não autentica nada, só prova que quem mandou a requisição consegue
    # ler cookies desta origem.
    response.set_cookie(
        ADMIN_CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )

    # O token continua no corpo para não quebrar quem autentica por bearer
    # (scripts, curl, o job de verificação do CI). O painel ignora este
    # campo desde a migração para cookie.
    return AdminTokenResponse(access_token=token)


@router.post("/logout")
async def admin_logout(response: Response) -> dict:
    """
    Encerra a sessão do painel apagando os dois cookies.

    Não exige autenticação: quem chama já está deslogando, e um 401 aqui
    só deixaria o usuário preso com um cookie expirado que ele não
    consegue limpar. Não valida CSRF pelo mesmo motivo — o pior que um
    CSRF consegue nesta rota é deslogar a vítima.
    """
    response.delete_cookie(ADMIN_TOKEN_COOKIE, path="/")
    response.delete_cookie(ADMIN_CSRF_COOKIE, path="/")
    return {"message": "Sessão encerrada"}


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> StatsResponse:
    service = AdminService(db)
    stats = await service.get_stats()
    return StatsResponse(**stats)


@router.get("/candidatos")
async def list_candidatos(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> list[dict]:
    service = AdminService(db)
    candidatos = await service.list_candidatos()
    return [
        {
            "id": c.id,
            "nome": c.nome,
            "apelido": c.apelido,
            "foto": c.foto,
            "ativo": c.ativo,
        }
        for c in candidatos
    ]


@router.post("/candidatos")
async def create_candidato(
    nome: str = Form(...),
    apelido: str = Form(...),
    ativo: bool = Form(default=True),
    foto: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> dict:
    service = AdminService(db)
    try:
        candidato = await service.create_candidato(nome, apelido, ativo, foto)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"id": candidato.id, "message": "Candidato criado"}


@router.put("/candidatos/{candidato_id}")
async def update_candidato(
    candidato_id: int,
    nome: str | None = Form(default=None),
    apelido: str | None = Form(default=None),
    ativo: bool | None = Form(default=None),
    foto: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> dict:
    service = AdminService(db)
    try:
        candidato = await service.update_candidato(
            candidato_id, nome, apelido, ativo, foto
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not candidato:
        raise HTTPException(status_code=404, detail="Candidato não encontrado")

    return {"message": "Candidato atualizado"}


@router.get("/search")
async def search_cpf(
    cpf: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> list[dict]:
    service = AdminService(db)
    results = await service.search_cpf(cpf)
    return [
        {
            "id": a.id,
            "nome": a.nome,
            "cpf": a.cpf,
            "numero_socio": a.numero_socio,
            "telefone": a.telefone,
            "departamentos": [
                ad.departamento.nome
                for ad in sorted(a.departamentos, key=lambda x: x.departamento.ordem)
            ],
            "departamento_outros": a.departamento_outros or "",
            "data_resposta": format_datetime_br(a.data_resposta),
            "candidatos": [r.candidato.nome for r in a.respostas],
            "preferido": a.preferencia.candidato_preferido.nome if a.preferencia else None,
        }
        for a in results
    ]


@router.get("/export/csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> Response:
    service = ExportService(db)
    content = await service.export_csv()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=respostas.csv"},
    )


@router.get("/export/excel")
async def export_excel(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> Response:
    service = ExportService(db)
    content = await service.export_excel()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=respostas.xlsx"},
    )


# Exportações agregadas: mesmo conteúdo das de cima menos TODO identificador
# pessoal. Para quem só precisa do resultado da sondagem, é o arquivo certo a
# entregar — não há motivo para repassar CPF e telefone de associado junto de
# uma contagem de votos.
@router.get("/export/resultados/csv")
async def export_resultados_csv(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> Response:
    service = ExportService(db)
    content = await service.export_resultados_csv()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=resultados.csv"},
    )


@router.get("/export/resultados/excel")
async def export_resultados_excel(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_admin_token),
) -> Response:
    service = ExportService(db)
    content = await service.export_resultados_excel()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=resultados.xlsx"},
    )
