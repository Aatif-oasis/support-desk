import uuid

from sqlalchemy import Boolean, Column, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class Permission(Base, AuditMixin):
    """
    Platform-global — permissions are defined once by the platform, not
    per-organization. e.g. code="conversations.assign", "tickets.close".
    """
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)


class Role(Base, AuditMixin):
    """
    organization_id is NULL for system roles (super_admin, org_admin,
    team_manager, agent) that every organization gets by default.
    Organizations may also define custom roles scoped to themselves.
    """
    __tablename__ = "roles"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
)
