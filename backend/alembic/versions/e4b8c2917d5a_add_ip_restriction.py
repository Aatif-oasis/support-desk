"""add per-user IP restriction

Revision ID: e4b8c2917d5a
Revises: c1a7f4e93b20
Create Date: 2026-09-14

Three nullable columns on users. Nullable matters: every account that
exists when this runs keeps working exactly as before, and the lock only
applies to accounts an admin has deliberately pinned to an address.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4b8c2917d5a"
down_revision: Union[str, None] = "c1a7f4e93b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 45 characters: long enough for an IPv6 address written in full.
    op.add_column("users", sa.Column("allowed_ip", sa.String(length=45), nullable=True))
    op.add_column("users", sa.Column("last_blocked_ip", sa.String(length=45), nullable=True))
    op.add_column(
        "users", sa.Column("last_blocked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "last_blocked_at")
    op.drop_column("users", "last_blocked_ip")
    op.drop_column("users", "allowed_ip")
