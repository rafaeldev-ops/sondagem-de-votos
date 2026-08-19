import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_db, get_otp_service, get_user_agent
from app.core.config import get_settings
from app.core.limiter import limiter
from app.integrations.recaptcha import RecaptchaService
from app.repositories import AssociadoRepository, CandidatoRepository, DepartamentoRepository
from app.schemas import (
    CadastroRequest,
    CPFValidateRequest,
    MessageResponse,
    OTPResendRequest,
    OTPVerifyRequest,
    SessionResponse,
    VotoRequest,
)
from app.services.otp_service import OTPService
from app.services.survey_service import SurveyService
from app.utils.cpf import validate_cpf, normalize_cpf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/survey", tags=["Survey"])

# Lido no import: os decorators @limiter.limit(...) abaixo são avaliados no
# momento em que o módulo é carregado, então precisam de um objeto de
# settings já disponível aqui (get_settings é cacheado com lru_cache).
_settings = get_settings()

@router.post("/validate-cpf")
@limiter.limit(_settings.rate_limit_validate_cpf)
async def validate_cpf_endpoint(
    request: Request,
    body: CPFValidateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    cpf = normalize_cpf(body.cpf)
    if not validate_cpf(cpf):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CPF inválido")

    existing = await AssociadoRepository(db).get_by_cpf(cpf)
    available = existing is None
    msg = "Este CPF já participou da sondagem" if not available else None

    return {
        "valid": True,
        "available": available,
        "message": msg,
    }


@router.post("/register", response_model=SessionResponse)
@limiter.limit(_settings.rate_limit_register)
async def register(
    request: Request,
    body: CadastroRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
) -> SessionResponse:
    recaptcha = RecaptchaService()
    ip = await get_client_ip(request)
    if not await recaptcha.verify(body.recaptcha_token, ip):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verificação reCAPTCHA falhou")

    service = SurveyService(db, otp_service)
    session_token, error = await service.register_and_send_otp(
        nome=body.nome,
        cpf=body.cpf,
        telefone=body.telefone,
        numero_socio=body.numero_socio,
        titular=body.titular,
        ip=ip,
        user_agent=get_user_agent(request),
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return SessionResponse(
        session_token=session_token,  # type: ignore[arg-type]
        message="Código OTP enviado para seu celular",
    )


@router.post("/verify-otp", response_model=MessageResponse)
@limiter.limit(_settings.rate_limit_verify_otp)
async def verify_otp(
    request: Request,
    body: OTPVerifyRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
) -> MessageResponse:
    service = SurveyService(db, otp_service)
    valid, error = await service.verify_otp(
        telefone=body.telefone,
        codigo=body.codigo,
        session_token=body.session_token,
        ip=await get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return MessageResponse(message="Autenticação realizada com sucesso")


@router.post("/resend-otp", response_model=MessageResponse)
@limiter.limit(_settings.rate_limit_resend_otp)
async def resend_otp(
    request: Request,
    body: OTPResendRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
) -> MessageResponse:
    service = SurveyService(db, otp_service)
    success, error = await service.resend_otp(body.telefone, body.session_token)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return MessageResponse(message="Novo código enviado")


@router.get("/candidatos")
async def list_candidatos(db: AsyncSession = Depends(get_db)) -> list[dict]:
    repo = CandidatoRepository(db)
    candidatos = await repo.list_active()
    return [
        {
            "id": c.id,
            "nome": c.nome,
            "apelido": c.apelido,
            "foto": c.foto or "/static/img/placeholder.svg",
        }
        for c in candidatos
    ]


@router.get("/departamentos")
async def list_departamentos(db: AsyncSession = Depends(get_db)) -> list[dict]:
    repo = DepartamentoRepository(db)
    departamentos = await repo.list_active()
    return [{"id": d.id, "nome": d.nome} for d in departamentos]


@router.post("/submit", response_model=MessageResponse)
@limiter.limit(_settings.rate_limit_submit)
async def submit_vote(
    request: Request,
    body: VotoRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
) -> MessageResponse:
    service = SurveyService(db, otp_service)
    success, error = await service.submit_vote(
        session_token=body.session_token,
        candidatos_ids=body.candidatos_ids,
        candidato_preferido_id=body.candidato_preferido_id,
        departamentos_ids=body.departamentos_ids,
        departamento_outros=body.departamento_outros,
        aceite_lgpd=body.aceite_lgpd,
        ip=await get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return MessageResponse(message="Resposta registrada com sucesso")
