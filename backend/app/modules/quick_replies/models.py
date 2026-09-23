import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class QuickReply(Base, AuditMixin):
    """
    A canned response template, e.g. title="Greeting", content="Hi! Thanks
    for reaching out...". Agents fetch the org's list and insert one
    verbatim (or edit before sending) — this table just stores the
    template; sending it is still a normal POST to /conversations/{id}/messages.
    """
    __tablename__ = "quick_replies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
