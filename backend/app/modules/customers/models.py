import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class Customer(Base, AuditMixin):
    """
    A website visitor/customer, NOT a platform User — they never log into
    the dashboard. Created (or matched) via the public /identify endpoint
    when the chat widget first loads on a page, keyed by external_id (a
    widget-generated id persisted in a cookie/localStorage on the
    customer's browser — NOT a login).

    Fields map directly to the "Customer Features" list in the original
    spec: profile, visit history basics, browser/OS/geo/locale, contact
    fields, tags, notes.
    """
    __tablename__ = "customers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Identity — all nullable since an anonymous visitor starts with none of this
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Session/device context — captured by the widget on each identify call
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operating_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_page: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Agent-managed
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
