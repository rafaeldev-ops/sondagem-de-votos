"""Add associados.titular

Revision ID: 007
Revises: 006
Create Date: 2026-08-07

Como a 006 (e ao contrário da 004), esta migration roda com a sondagem em
produção e votos já coletados: a coluna é nullable e sem server_default.

O NULL é significativo e não é preguiça de escrever um default: ele é o
"não perguntado" das respostas anteriores a esta pergunta. Marcar as linhas
antigas como False diria que aquelas pessoas se declararam dependentes, o
que nenhuma delas fez — e essa mentira sairia na exportação como um "Não"
indistinguível de uma resposta real.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("associados", sa.Column("titular", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("associados", "titular")
