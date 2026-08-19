"""Add missing indexes on FK columns and pipefy_logs.status

Postgres does not automatically index foreign key columns (only the
referenced side, via the primary key). The composite UNIQUE constraint on
respostas(associado_id, candidato_id) already backs lookups by
associado_id (leftmost column), and the UNIQUE on preferencias.associado_id
already backs that column — those are NOT duplicated here. What actually
had no index at all:

- respostas.candidato_id (not the leftmost column of the composite unique,
  so lookups filtered only by candidato_id do a sequential scan)
- preferencias.candidato_preferido_id
- pipefy_logs.associado_id
- pipefy_logs.status (filtered constantly by list_pending())

Revision ID: 002
Revises: 001
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_respostas_candidato_id", "respostas", ["candidato_id"])
    op.create_index(
        "ix_preferencias_candidato_preferido_id", "preferencias", ["candidato_preferido_id"]
    )
    op.create_index("ix_pipefy_logs_associado_id", "pipefy_logs", ["associado_id"])
    # Índice parcial: list_pending() só filtra por status in ('pending','failed'),
    # nunca por 'sent' — um índice parcial cobre exatamente o que é consultado
    # e fica menor / mais rápido de manter do que indexar a coluna inteira.
    op.create_index(
        "ix_pipefy_logs_status_pending",
        "pipefy_logs",
        ["status"],
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("ix_pipefy_logs_status_pending", table_name="pipefy_logs")
    op.drop_index("ix_pipefy_logs_associado_id", table_name="pipefy_logs")
    op.drop_index("ix_preferencias_candidato_preferido_id", table_name="preferencias")
    op.drop_index("ix_respostas_candidato_id", table_name="respostas")
