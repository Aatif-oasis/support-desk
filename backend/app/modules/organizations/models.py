from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class Organization(Base, AuditMixin):
    """
    The root tenant entity. Organizations does NOT use TenantMixin — it IS
    the tenant boundary, not something scoped by one. Only Super Admin
    (users.organization_id IS NULL) can create/manage rows in this table.
    """
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    subscription_plan: Mapped[str] = mapped_column(String(50), default="trial", nullable=False)
    subscription_status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
