import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class Conversation(Base, AuditMixin):
    """
    One chat thread between a Customer and (eventually) an assigned Agent.
    channel is a plain string rather than an enum table since the widget is
    the only channel that exists right now — more channels (email, etc.)
    are a later-roadmap concern and this column just needs to hold their name.
    """
    __tablename__ = "conversations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(50), default="widget", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Read receipts. Stored as one "last seen" timestamp per side rather
    # than a read flag on every message: a chat is read top to bottom, so
    # one timestamp answers "has this been seen?" for every message at
    # once, and marking read stays a single row update no matter how long
    # the conversation is.
    customer_last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agent_last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Tag(Base, AuditMixin):
    """Org-scoped, reusable across conversations. name unique per org."""
    __tablename__ = "tags"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)


conversation_tags = Table(
    "conversation_tags",
    Base.metadata,
    Column("conversation_id", UUID(as_uuid=True), ForeignKey("conversations.id"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True),
)


class ConversationNote(Base, AuditMixin):
    """
    Agent-only, never visible to the customer — distinct from
    Customer.notes (which is about the person across all their
    conversations). This is scoped to one specific conversation, e.g.
    "Checked their account, billing issue confirmed, escalating."
    """
    __tablename__ = "conversation_notes"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)


class Message(Base, AuditMixin):
    """
    sender_type distinguishes who wrote it since a message's author is
    EITHER a Customer OR a User (agent) OR the system itself (e.g. "Agent
    joined the conversation") — never more than one FK is meaningfully
    populated, so this uses a discriminator + a single nullable sender_id
    rather than two separate nullable FK columns.
    """
    __tablename__ = "messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)  # customer|agent|system
    sender_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
