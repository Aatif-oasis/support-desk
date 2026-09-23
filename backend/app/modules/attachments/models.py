import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class Attachment(Base, AuditMixin):
    """
    Always belongs to exactly one Message — an attachment without a
    message doesn't make sense in a chat product (matches the "Images /
    Videos / Documents / Audio messages" attachment types from the spec).
    storage_path is opaque and only meaningful to whichever StorageBackend
    wrote it (see storage.py) — never construct a filesystem path from it
    directly outside that module.
    """
    __tablename__ = "attachments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
