import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class User(Base, AuditMixin):
    """
    organization_id is NULL only for Super Admin accounts — every other
    platform user (Org Admin, Team Manager, Agent) belongs to exactly one
    organization. Customers are NOT users — see modules/customers.
    """
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Office lock. NULL means "no restriction" — deliberately, because the
    # opposite default would lock out every existing account the moment
    # this shipped. Set by an admin, and only ever enforced for agents and
    # team managers: an admin who typed their own address wrong would have
    # no way back in, since they are the only one who can undo it.
    allowed_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # So an admin can see that someone tried from the wrong place, rather
    # than only hearing about it when the agent complains they can't log in.
    last_blocked_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    last_blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
