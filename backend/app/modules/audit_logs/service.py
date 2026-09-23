import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_logs.models import AuditLog
from app.modules.audit_logs.repository import AuditLogRepository


class AuditLogService:
    """
    Deliberately has no dependency on any other module — other services
    import AND call this (one-directional), never the reverse. That's
    what makes it safe to call from users/service.py, organizations/service.py,
    auth/service.py, etc. without any circular-import risk.
    """

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = AuditLogRepository(session, organization_id=organization_id)

    async def log(
        self,
        actor_user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        extra_data: dict | None = None,
    ) -> None:
        """
        Does NOT commit — the caller's own transaction commit covers this
        row too, so an audit entry never gets written for a mutation that
        itself rolled back.
        """
        await self.repo.create(
            AuditLog(
                organization_id=self.organization_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                extra_data=extra_data or {},
            )
        )

    async def list_logs(
        self, entity_type: str | None, action: str | None, limit: int, offset: int
    ) -> list[AuditLog]:
        return await self.repo.list_filtered(entity_type, action, limit, offset)
