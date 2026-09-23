"""add read receipt columns to conversations

Revision ID: c1a7f4e93b20
Revises: 7539617d621d
Create Date: 2026-09-08

Two nullable timestamps rather than a per-message read flag. A chat is
read top to bottom, so one "last seen" time per side answers the question
for every message at once, and marking a chat read stays a single row
update however long the thread grows.

Both start NULL, which correctly means "nothing seen yet" for every
conversation that existed before this ran.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a7f4e93b20"
down_revision: Union[str, None] = "7539617d621d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("customer_last_read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("agent_last_read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "agent_last_read_at")
    op.drop_column("conversations", "customer_last_read_at")
