from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.audit_logs.schemas import AuditLogResponse
from app.modules.audit_logs.service import AuditLogService
from app.modules.auth.dependencies import CurrentUser, require_roles

router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    entity_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> list[AuditLogResponse]:
    logs = await AuditLogService(db, current_user.organization_id).list_logs(
        entity_type, action, limit, offset
    )
    return [AuditLogResponse.model_validate(l) for l in logs]
