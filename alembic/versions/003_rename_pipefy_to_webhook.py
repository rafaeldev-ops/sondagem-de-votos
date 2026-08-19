"""Rename pipefy_logs to webhook_logs

Revision ID: 003
Revises: 002
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("pipefy_logs", "webhook_logs")


def downgrade() -> None:
    op.rename_table("webhook_logs", "pipefy_logs")
