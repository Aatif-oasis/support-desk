import uuid

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class Team(Base, AuditMixin):
    __tablename__ = "teams"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


# Join table: which users belong to which teams (many-to-many)
user_teams = Table(
    "user_teams",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("team_id", UUID(as_uuid=True), ForeignKey("teams.id"), primary_key=True),
)
