from app.modules.audit_logs.models import AuditLog
from app.shared.base_repository import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def list_filtered(
        self, entity_type: str | None, action: str | None, limit: int, offset: int
    ) -> list[AuditLog]:
        query = self._base_query().order_by(AuditLog.created_at.desc())
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if action:
            query = query.where(AuditLog.action == action)
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
