"""Rename remaining pipefy_* database objects to webhook_*

Revision ID: 005
Revises: 004
Create Date: 2026-08-07

A 003 renomeou a tabela com op.rename_table, mas no Postgres renomear uma
tabela não renomeia os objetos pendurados nela: índices, constraints e a
sequence do SERIAL mantêm o nome com que foram criados. O resultado é uma
webhook_logs cujos objetos internos ainda se chamam pipefy_*.

Hoje isso não quebra nada — nenhum código cita esses nomes. O problema é a
divergência entre ambientes, a mesma que motivou nomear explicitamente a
uq_associados_numero_socio: os testes criam o schema por
Base.metadata.create_all, que gera "webhook_logs_pkey" e
"webhook_logs_associado_id_fkey", enquanto produção, vindo do Alembic, tem
"pipefy_logs_pkey" e "pipefy_logs_associado_id_fkey". Uma migration futura
que referencie qualquer um desses nomes passaria no teste e falharia em
produção.

O downgrade precisa ser um inverso fiel: o downgrade da 002 dropa os índices
pelos nomes antigos (ix_pipefy_logs_*), então descer abaixo da 002 só
funciona se esta migration tiver devolvido os nomes originais antes.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A PK entra só como constraint: renomear a constraint de chave primária
    # renomeia junto o índice que a sustenta, que tem sempre o nome dela.
    op.execute(
        "ALTER TABLE webhook_logs RENAME CONSTRAINT pipefy_logs_pkey "
        "TO webhook_logs_pkey"
    )
    op.execute(
        "ALTER TABLE webhook_logs RENAME CONSTRAINT pipefy_logs_associado_id_fkey "
        "TO webhook_logs_associado_id_fkey"
    )
    op.execute(
        "ALTER INDEX ix_pipefy_logs_associado_id RENAME TO ix_webhook_logs_associado_id"
    )
    op.execute(
        "ALTER INDEX ix_pipefy_logs_status_pending "
        "RENAME TO ix_webhook_logs_status_pending"
    )
    # Criada pelo SERIAL da coluna id, com o nome da tabela de origem.
    op.execute("ALTER SEQUENCE pipefy_logs_id_seq RENAME TO webhook_logs_id_seq")


def downgrade() -> None:
    op.execute("ALTER SEQUENCE webhook_logs_id_seq RENAME TO pipefy_logs_id_seq")
    op.execute(
        "ALTER INDEX ix_webhook_logs_status_pending "
        "RENAME TO ix_pipefy_logs_status_pending"
    )
    op.execute(
        "ALTER INDEX ix_webhook_logs_associado_id RENAME TO ix_pipefy_logs_associado_id"
    )
    op.execute(
        "ALTER TABLE webhook_logs RENAME CONSTRAINT webhook_logs_associado_id_fkey "
        "TO pipefy_logs_associado_id_fkey"
    )
    op.execute(
        "ALTER TABLE webhook_logs RENAME CONSTRAINT webhook_logs_pkey "
        "TO pipefy_logs_pkey"
    )
