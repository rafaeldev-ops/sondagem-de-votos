"""Drop webhook_logs

Revision ID: 008
Revises: 007
Create Date: 2026-08-07

O envio por webhook (n8n) foi removido: as exportações CSV/Excel já
entregavam tudo o que o payload levava, e mais o ID. Sem consumidor, a
tabela só acumulava uma linha `failed` por voto — com WEBHOOK_URL vazia,
`send_webhook` desistia antes de tentar e o registro nascia falho.

ATENÇÃO: esta migration APAGA DADOS. As linhas de webhook_logs guardam o
payload de cada voto em JSON (nome, CPF, telefone, em quem votou). Isso é
duplicata do que está nas tabelas normalizadas — `associados`, `respostas`,
`preferencias` e `associado_departamentos` seguem intactas, e as
exportações continuam completas. Nenhuma resposta de sócio se perde aqui.
Ainda assim, quem quiser guardar o histórico bruto deve fazer o dump da
tabela ANTES de rodar `alembic upgrade head`:

    pg_dump -t webhook_logs <banco> > webhook_logs.sql

O downgrade recria a estrutura (tabela, índices e FK, incluindo o índice
parcial de status criado na 002/005), mas devolve a tabela VAZIA — dado
apagado não volta por migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Os índices caem junto com a tabela; não é preciso derrubá-los antes.
    op.drop_table("webhook_logs")


def downgrade() -> None:
    op.create_table(
        "webhook_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("associado_id", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["associado_id"], ["associados.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_logs_associado_id", "webhook_logs", ["associado_id"]
    )
    # Índice parcial: só as linhas que o worker de retry buscava.
    op.create_index(
        "ix_webhook_logs_status_pending",
        "webhook_logs",
        ["status"],
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )
