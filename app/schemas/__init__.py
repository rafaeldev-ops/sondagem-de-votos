from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.utils.cpf import normalize_cpf, validate_cpf
from app.utils.phone import normalize_phone, validate_phone
from app.utils.sanitize import sanitize_text
from app.utils.socio import normalize_numero_socio, validate_numero_socio


class CPFValidateRequest(BaseModel):
    cpf: str

    @field_validator("cpf")
    @classmethod
    def validate_cpf_field(cls, value: str) -> str:
        cpf = normalize_cpf(value)
        if not validate_cpf(cpf):
            raise ValueError("CPF inválido")
        return cpf


class CadastroRequest(BaseModel):
    nome: str = Field(min_length=3, max_length=255)
    cpf: str
    numero_socio: str
    telefone: str
    # Sem default, ao contrário de recaptcha_token: o formulário sempre manda
    # os dois estados do checkbox (marcado/desmarcado), então payload sem o
    # campo é bug de frontend e deve estourar 422 na hora. Um default False
    # aqui gravaria "não é titular" para quem nunca foi perguntado — o mesmo
    # erro que a migration 007 evita no banco.
    titular: bool
    recaptcha_token: str = Field(default="")

    @field_validator("nome")
    @classmethod
    def sanitize_nome(cls, value: str) -> str:
        return sanitize_text(value, 255)

    @field_validator("cpf")
    @classmethod
    def validate_cpf_field(cls, value: str) -> str:
        cpf = normalize_cpf(value)
        if not validate_cpf(cpf):
            raise ValueError("CPF inválido")
        return cpf

    @field_validator("numero_socio")
    @classmethod
    def validate_numero_socio_field(cls, value: str) -> str:
        numero = normalize_numero_socio(value)
        if not validate_numero_socio(numero):
            raise ValueError("Número de sócio deve ter exatamente 4 dígitos")
        return numero

    @field_validator("telefone")
    @classmethod
    def validate_telefone(cls, value: str) -> str:
        phone = normalize_phone(value)
        if not validate_phone(phone):
            raise ValueError("Telefone inválido")
        return phone


class OTPVerifyRequest(BaseModel):
    telefone: str
    codigo: str = Field(min_length=6, max_length=6)
    session_token: str

    @field_validator("telefone")
    @classmethod
    def validate_telefone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("codigo")
    @classmethod
    def validate_codigo(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Código deve conter apenas dígitos")
        return value


class OTPResendRequest(BaseModel):
    telefone: str
    session_token: str

    @field_validator("telefone")
    @classmethod
    def validate_telefone(cls, value: str) -> str:
        return normalize_phone(value)


class VotoRequest(BaseModel):
    session_token: str
    candidatos_ids: list[int] = Field(min_length=1, max_length=20)
    candidato_preferido_id: int
    # min_length=1 é a obrigatoriedade da etapa; max_length=49 é o total de
    # opções da lista e existe só para recusar payload absurdo.
    departamentos_ids: list[int] = Field(min_length=1, max_length=49)
    departamento_outros: str = Field(default="", max_length=100)
    # Opt-in de contato, não condição para participar da sondagem: desmarcado
    # é a resposta "não quero receber notícias", do mesmo jeito que o
    # checkbox "titular" trata desmarcado como resposta e não omissão.
    aceite_lgpd: bool

    @field_validator("departamento_outros")
    @classmethod
    def sanitize_departamento_outros(cls, value: str) -> str:
        # Primeiro texto livre do fluxo público — mesmo tratamento que o nome.
        return sanitize_text(value, 100)


class CandidatoPublic(BaseModel):
    id: int
    nome: str
    apelido: str
    foto: str | None

    model_config = {"from_attributes": True}


class CandidatoCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=255)
    apelido: str = Field(min_length=1, max_length=100)
    ativo: bool = True

    @field_validator("nome", "apelido")
    @classmethod
    def sanitize_fields(cls, value: str) -> str:
        return sanitize_text(value, 255)


class CandidatoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=255)
    apelido: str | None = Field(default=None, min_length=1, max_length=100)
    ativo: bool | None = None


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StatsResponse(BaseModel):
    total_respostas: int
    total_candidatos_ativos: int
    total_candidatos: int


class AssociadoResponse(BaseModel):
    id: int
    nome: str
    cpf: str
    numero_socio: str
    telefone: str
    # None = respondeu antes da pergunta existir (ver migration 007).
    titular: bool | None = None
    data_resposta: datetime
    candidatos: list[str]
    preferido: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class SessionResponse(BaseModel):
    session_token: str
    message: str


class ResultadoCandidato(BaseModel):
    """Uma linha do resultado agregado — sem nenhum identificador pessoal."""

    nome: str
    apelido: str
    votos: int
    percentual: float
    ponto_focal: int
