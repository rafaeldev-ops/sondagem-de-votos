# Guia de Instalação

## Pré-requisitos

- Docker 24+ e Docker Compose v2
- Ou: Python 3.12+, PostgreSQL 16+, Redis 7+

## Instalação com Docker (recomendado)

### 1. Clone e configure

```bash
git clone <repo-url> sondagem-clube-votos
cd sondagem-clube-votos
cp .env.example .env
```

### 2. Edite o `.env`

Variáveis obrigatórias:

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | Chave secreta longa e aleatória |
| `ADMIN_USERNAME` | Usuário do painel admin |
| `ADMIN_PASSWORD` | Senha do admin (texto ou hash bcrypt) |

Para produção, gere hash bcrypt:

```bash
python scripts/hash_password.py "sua-senha-forte"
```

Cole o hash em `ADMIN_PASSWORD`.

### 3. Configure OTP

Defina `OTP_PROVIDER` como `twilio`, `zenvia`, `zapi` ou `mock` (desenvolvimento).

**Twilio:**
```
OTP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+5511...
```

**Zenvia:**
```
OTP_PROVIDER=zenvia
ZENVIA_API_TOKEN=...
ZENVIA_FROM=...
```

**Z-API:**
```
OTP_PROVIDER=zapi
ZAPI_INSTANCE_ID=...
ZAPI_TOKEN=...
ZAPI_CLIENT_TOKEN=...
```

### 4. Configure reCAPTCHA v3

1. Acesse https://www.google.com/recaptcha/admin
2. Crie um site reCAPTCHA v3
3. Configure:
```
RECAPTCHA_SITE_KEY=...
RECAPTCHA_SECRET_KEY=...
```

Em desenvolvimento sem chaves, o backend aceita bypass quando `DEBUG=true`.

### 5. Suba os serviços

```bash
docker compose up -d --build
docker compose exec app alembic upgrade head
```

### 6. Cadastre candidatos

Acesse http://localhost:8000/admin e adicione os candidatos com fotos.

## Instalação manual

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Crie o banco PostgreSQL
createdb sondagem_clube

# Configure DATABASE_URL e DATABASE_URL_SYNC no .env
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Verificação

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Troubleshooting

| Problema | Solução |
|----------|---------|
| OTP não enviado | Verifique credenciais do provider; use `OTP_PROVIDER=mock` para testes |
| Erro de conexão DB | Aguarde healthcheck do PostgreSQL; verifique `DATABASE_URL` |
| reCAPTCHA falha | Confirme domínio registrado no Google reCAPTCHA |
