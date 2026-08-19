"""Add departamentos, associado_departamentos and departamento_outros

Revision ID: 006
Revises: 005
Create Date: 2026-08-07

Ao contrário da 004, esta migration NÃO exige que associados esteja vazia:
as duas tabelas são novas e a coluna nova é nullable. Roda com a sondagem
em produção e votos já coletados.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Lista oficial do clube. A ordem NÃO é alfabética e não deve ser
# reordenada: no bloco de ginástica, "Rítmica" vem antes de "Feminina /
# Fitness". A grafia também é a original ("Ginastica" sem acento, "Tenis de
# mesa", "Volei Masculino") e o separador é o travessão U+2013.
MODALIDADES = [
    "Academia / Musculação",
    "Atletismo",
    "Basquete – Feminino",
    "Basquete – Masculino",
    "Beach Tennis",
    "Biribol",
    "Boxe",
    "Capoeira",
    "Carteado",
    "COD",
    "COTI",
    "Esportes Amadores",
    "FAVA",
    "Fitness / Dança",
    "Futebol de Mesa",
    "Futebol Social – Feminino",
    "Futebol Social – Masculino",
    "Futebol Social – Menores",
    "Futebol Society – Feminino",
    "Futebol Society – Masculino",
    "Futevôlei",
    "Ginastica Aeróbica",
    "Ginastica Artística",
    "Ginastica Rítmica",
    "Ginastica Feminina / Fitness",
    "Handebol",
    "Hidroginástica",
    "Jiu Jitsu",
    "Judô",
    "Karaokê",
    "Kickboxing",
    "Natação",
    "Paddle",
    "Patinação",
    "Pickleball",
    "Piscina",
    "Polo Aquático",
    "Sauna",
    "Sinuca",
    "Social",
    "Tai Chi Chuan",
    "Teatro",
    "Tenis de mesa",
    "Tennis",
    "Triathlon",
    "Vôlei de Praia",
    "Vôlei Feminino",
    "Volei Masculino",
]


def upgrade() -> None:
    op.create_table(
        "departamentos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("exige_texto", sa.Boolean(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome", name="uq_departamentos_nome"),
    )

    op.create_table(
        "associado_departamentos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("associado_id", sa.Integer(), nullable=False),
        sa.Column("departamento_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["associado_id"], ["associados.id"]),
        sa.ForeignKeyConstraint(["departamento_id"], ["departamentos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "associado_id", "departamento_id", name="uq_associado_departamento"
        ),
    )
    op.create_index(
        "ix_associado_departamentos_associado_id",
        "associado_departamentos",
        ["associado_id"],
    )
    op.create_index(
        "ix_associado_departamentos_departamento_id",
        "associado_departamentos",
        ["departamento_id"],
    )

    op.add_column(
        "associados",
        sa.Column("departamento_outros", sa.String(length=100), nullable=True),
    )

    departamentos = sa.table(
        "departamentos",
        sa.column("nome", sa.String),
        sa.column("ordem", sa.Integer),
        sa.column("exige_texto", sa.Boolean),
        sa.column("ativo", sa.Boolean),
    )
    op.bulk_insert(
        departamentos,
        [
            {"nome": nome, "ordem": i, "exige_texto": False, "ativo": True}
            for i, nome in enumerate(MODALIDADES, start=1)
        ]
        + [{"nome": "Outros", "ordem": 999, "exige_texto": True, "ativo": True}],
    )


def downgrade() -> None:
    op.drop_column("associados", "departamento_outros")
    op.drop_index(
        "ix_associado_departamentos_departamento_id",
        table_name="associado_departamentos",
    )
    op.drop_index(
        "ix_associado_departamentos_associado_id", table_name="associado_departamentos"
    )
    # A associativa primeiro: ela é quem tem as FKs.
    op.drop_table("associado_departamentos")
    op.drop_table("departamentos")
