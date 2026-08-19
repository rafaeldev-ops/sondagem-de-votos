#!/usr/bin/env bash
#
# Exporta os dados de "seed" (candidatos + departamentos) para levar ao
# banco de produção, SEM os dados de teste do ambiente de desenvolvimento
# (associados, respostas, preferências, audit_logs).
#
# Uso:
#   ./scripts/export_seed_candidatos.sh
#   OUT_DIR=/algum/lugar ./scripts/export_seed_candidatos.sh
#
# Gera dois arquivos em OUT_DIR:
#   - seed_candidatos_departamentos.sql  (INSERT dos candidatos/departamentos)
#   - fotos_candidatos.tar.gz            (conteúdo de uploads/candidatos)
#
# No servidor de produção, depois de "alembic upgrade head":
#   docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" \
#     < seed_candidatos_departamentos.sql
#   tar -xzf fotos_candidatos.tar.gz -C uploads/candidatos/

set -euo pipefail

OUT_DIR="${OUT_DIR:-./backups}"

# Só lê POSTGRES_USER/POSTGRES_DB do .env, sem dar "source" no arquivo
# inteiro: APP_NAME=SEMPRE TRICOLOR (valor com espaço, sem aspas) quebra o
# "source ./.env" usado em scripts/backup.sh.
if [ -f .env ] && [ -z "${POSTGRES_USER:-}" ]; then
    POSTGRES_USER=$(grep -m1 '^POSTGRES_USER=' .env | cut -d= -f2-)
fi
if [ -f .env ] && [ -z "${POSTGRES_DB:-}" ]; then
    POSTGRES_DB=$(grep -m1 '^POSTGRES_DB=' .env | cut -d= -f2-)
fi

: "${POSTGRES_USER:?defina POSTGRES_USER (no .env ou no ambiente)}"
: "${POSTGRES_DB:?defina POSTGRES_DB (no .env ou no ambiente)}"

mkdir -p "$OUT_DIR"
SQL_FILE="$OUT_DIR/seed_candidatos_departamentos.sql"
PHOTOS_FILE="$OUT_DIR/fotos_candidatos.tar.gz"

echo "Exportando candidatos e departamentos para $SQL_FILE ..."
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
    --data-only --column-inserts \
    -t departamentos -t candidatos \
    > "$SQL_FILE"

SIZE=$(stat -c%s "$SQL_FILE" 2>/dev/null || stat -f%z "$SQL_FILE")
if [ "$SIZE" -lt 200 ]; then
    echo "ERRO: export suspeito (${SIZE} bytes). Verifique se o container 'db' está no ar." >&2
    exit 1
fi

echo "Compactando fotos de uploads/candidatos/ para $PHOTOS_FILE ..."
tar -czf "$PHOTOS_FILE" -C uploads candidatos

echo "Concluído:"
echo "  $SQL_FILE ($(du -h "$SQL_FILE" | cut -f1))"
echo "  $PHOTOS_FILE ($(du -h "$PHOTOS_FILE" | cut -f1))"
