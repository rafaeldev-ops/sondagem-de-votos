#!/usr/bin/env bash
#
# Zera votos e associados de TESTE antes do lancamento publico da sondagem,
# mantendo candidatos e departamentos intactos.
#
# Uso pretendido: apos o deploy, votar de verdade (celular real, para
# confirmar que o SMS do OTP chega) para validar o fluxo ponta a ponta, e
# so entao rodar este script antes de divulgar o link para os socios.
#
# Uso:
#   ./scripts/reset_votos_teste.sh
#
# Faz backup automatico antes (scripts/backup.sh) e pede confirmacao
# digitada, porque e destrutivo e irreversivel sem o backup.

set -euo pipefail

if [ -f .env ] && [ -z "${POSTGRES_USER:-}" ]; then
    POSTGRES_USER=$(grep -m1 '^POSTGRES_USER=' .env | cut -d= -f2-)
fi
if [ -f .env ] && [ -z "${POSTGRES_DB:-}" ]; then
    POSTGRES_DB=$(grep -m1 '^POSTGRES_DB=' .env | cut -d= -f2-)
fi
: "${POSTGRES_USER:?defina POSTGRES_USER (no .env ou no ambiente)}"
: "${POSTGRES_DB:?defina POSTGRES_DB (no .env ou no ambiente)}"

echo "Isto vai APAGAR PERMANENTEMENTE todos os associados, respostas,"
echo "preferencias e logs de auditoria do banco '$POSTGRES_DB'."
echo "Candidatos e departamentos NAO sao afetados."
echo

read -r -p "Fazer backup antes? [S/n] " fazer_backup
if [ "${fazer_backup:-s}" != "n" ] && [ "${fazer_backup:-s}" != "N" ]; then
    ./scripts/backup.sh
else
    echo "Prosseguindo SEM backup — se algo der errado, não há como voltar atrás."
fi

echo
read -r -p "Digite ZERAR para confirmar (qualquer outra coisa cancela): " confirmacao
if [ "$confirmacao" != "ZERAR" ]; then
    echo "Cancelado."
    exit 1
fi

docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "TRUNCATE respostas, preferencias, associado_departamentos, associados, audit_logs RESTART IDENTITY CASCADE;"

echo
echo "Conferindo:"
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "SELECT (SELECT count(*) FROM associados) AS associados, \
            (SELECT count(*) FROM respostas) AS respostas, \
            (SELECT count(*) FROM candidatos) AS candidatos;"

echo
echo "Pronto: associados e respostas zerados, candidatos preservados."
