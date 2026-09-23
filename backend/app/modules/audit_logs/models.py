import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class AuditLog(Base, AuditMixin):
    """
    Append-only record of admin-relevant actions (who did what, to what).
    Written by AuditLogService.log(), called from the services that own
    security-sensitive mutations (user management, role changes, org
    status, API keys) — not instrumented on every single write in every
    module, since most conversation/message activity isn't an "admin
    accountability" concern the way access/permission changes are.
    """
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
