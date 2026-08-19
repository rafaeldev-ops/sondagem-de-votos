# --- Stage 1: build (com toolchain de compilação) ---
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala tudo dentro de uma venv própria, não no site-packages do sistema.
# Uma venv é uma estrutura autocontida e previsível (bin/, lib/pythonX.Y/
# site-packages/) independente de particularidades de sysconfig da imagem
# base — copiar a venv inteira para o stage final é o padrão mais robusto
# para builds multi-stage em Python, sem depender de onde exatamente
# `pip install --prefix=...` decide instalar os pacotes.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# --- Stage 2: runtime (sem toolchain de build, roda como usuário não-root) ---
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libpq5 é a lib de runtime do client Postgres (psycopg2 precisa dela);
# gcc/libpq-dev (headers de build) ficaram só no stage anterior.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home /app app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

RUN mkdir -p uploads/candidatos static/uploads/candidatos \
    && chown -R app:app uploads static

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
