"""Add numero_socio to associados

Revision ID: 004
Revises: 003
Create Date: 2026-08-06

Pré-condição: a tabela associados precisa estar vazia. A coluna entra como
NOT NULL sem server_default, o que o Postgres recusa se houver linhas. Foi
uma decisão consciente (o sistema ainda não coletou votos em produção); se
isso mudar antes do deploy, esta migration precisa virar coluna nulável +
backfill.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "associados",
        sa.Column("numero_socio", sa.String(length=4), nullable=False),
    )
    op.create_unique_constraint(
        "uq_associados_numero_socio", "associados", ["numero_socio"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_associados_numero_socio", "associados", type_="unique")
    op.drop_column("associados", "numero_socio")
