"""
Every model in every module inherits AuditMixin (directly or via TenantMixin).
This is what gives the whole system consistent UUID PKs, created/updated
timestamps, soft deletes, and created_by/updated_by tracking without each
module reimplementing it — per the non-functional requirement that every
table carries audit fields.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class AuditMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class TenantMixin(AuditMixin):
    """
    Adds organization_id to AuditMixin. Every module EXCEPT Organizations
    itself (and platform-global tables like `permissions`) uses this mixin
    instead of AuditMixin directly — it's what BaseRepository relies on to
    auto-scope every query by tenant.
    """
    @staticmethod
    def organization_fk() -> Mapped[uuid.UUID]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
