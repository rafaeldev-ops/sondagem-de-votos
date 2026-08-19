"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "associados",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("cpf", sa.String(length=11), nullable=False),
        sa.Column("telefone", sa.String(length=20), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("aceite_lgpd", sa.Boolean(), nullable=False),
        sa.Column("data_resposta", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cpf"),
    )
    op.create_index("ix_associados_cpf", "associados", ["cpf"])

    op.create_table(
        "candidatos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("apelido", sa.String(length=100), nullable=False),
        sa.Column("foto", sa.String(length=500), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evento", sa.String(length=100), nullable=False),
        sa.Column("detalhes", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "respostas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("associado_id", sa.Integer(), nullable=False),
        sa.Column("candidato_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["associado_id"], ["associados.id"]),
        sa.ForeignKeyConstraint(["candidato_id"], ["candidatos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("associado_id", "candidato_id", name="uq_resposta_associado_candidato"),
    )

    op.create_table(
        "preferencias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("associado_id", sa.Integer(), nullable=False),
        sa.Column("candidato_preferido_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["associado_id"], ["associados.id"]),
        sa.ForeignKeyConstraint(["candidato_preferido_id"], ["candidatos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("associado_id"),
    )

    op.create_table(
        "pipefy_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("associado_id", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["associado_id"], ["associados.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pipefy_logs")
    op.drop_table("preferencias")
    op.drop_table("respostas")
    op.drop_table("audit_logs")
    op.drop_table("candidatos")
    op.drop_index("ix_associados_cpf", "associados")
    op.drop_table("associados")
