import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import PyJWTError
from passlib.context import CryptContext

from app.core.config import get_settings

# Nome dos cookies da sessão admin.
#
# ADMIN_TOKEN_COOKIE é httpOnly: o JWT não fica mais em localStorage, onde
# um XSS o leria com uma linha de script. httpOnly não impede o XSS de
# *usar* a sessão (o navegador anexa o cookie sozinho), mas impede que o
# token seja exfiltrado e reutilizado fora do navegador da vítima.
#
# ADMIN_CSRF_COOKIE é o oposto — precisa ser legível pelo JS, porque o
# admin.js copia o valor dele para o header X-CSRF-Token. Ver
# validate_csrf() em app/api/deps.py para o porquê disso funcionar.
ADMIN_TOKEN_COOKIE = "admin_token"
ADMIN_CSRF_COOKIE = "admin_csrf"
CSRF_HEADER = "X-CSRF-Token"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HS256 (HMAC-SHA256, simétrico): a mesma SECRET_KEY assina e valida. Não
# há chave pública envolvida, e nenhuma curva elíptica — foi por isso que
# a CVE da ecdsa nunca teve impacto real aqui, mesmo quando a lib vinha
# instalada junto.
#
# A biblioteca é PyJWT, não python-jose. A troca foi feita para eliminar
# ecdsa e pyasn1 da árvore de dependências: o python-jose exigia
# pyasn1<0.5.0 e as correções das 4 CVEs do pyasn1 só existem a partir da
# 0.6.3, então não havia como resolvê-las sem sair do python-jose.
ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.admin_jwt_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def generate_csrf_token() -> str:
    """Valor aleatório para o esquema de double submit cookie."""
    return secrets.token_urlsafe(32)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        # `algorithms` é obrigatório e fica restrito a HS256 de propósito:
        # aceitar o algoritmo declarado no header do próprio token é a
        # brecha clássica de confusão de algoritmo ("alg": "none", ou um
        # RS256 validado como HMAC usando a chave pública como segredo).
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except PyJWTError:
        # Cobre assinatura inválida, token malformado e expirado
        # (ExpiredSignatureError também herda de PyJWTError) — o contrato
        # desta função é devolver None em vez de propagar, e quem chama
        # (get_admin_token) traduz isso para 401.
        return None
