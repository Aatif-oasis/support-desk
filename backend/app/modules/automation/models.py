import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base_model import AuditMixin


class AutomationRule(Base, AuditMixin):
    """
    A rule: WHEN trigger_event fires, IF all conditions match, THEN run
    actions in order. Conditions/actions are JSON rather than normalized
    tables — this keeps the engine simple (no join explosion for what's
    fundamentally a small, rarely-queried config blob per rule) while still
    being fully data-driven, not hardcoded per org.

    conditions: [{"field": "message_content", "operator": "contains", "value": "refund"}, ...]
      (ALL must match — AND logic; empty list = always matches)
    actions: [{"type": "add_tag", "tag": "urgent"},
              {"type": "assign_agent", "agent_id": "<uuid>"},
              {"type": "auto_reply", "content": "..."}]
      (run in order)
    """
    __tablename__ = "automation_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    conditions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
