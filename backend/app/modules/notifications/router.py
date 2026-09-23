import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.notifications.schemas import NotificationResponse, UnreadCountResponse
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[NotificationResponse]:
    items = await NotificationService(db, current_user.organization_id).list_notifications(
        current_user.id, unread_only, limit, offset
    )
    return [NotificationResponse.model_validate(n) for n in items]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> UnreadCountResponse:
    count = await NotificationService(db, current_user.organization_id).unread_count(current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> None:
    await NotificationService(db, current_user.organization_id).mark_read(
        notification_id, current_user.id
    )


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> None:
    await NotificationService(db, current_user.organization_id).mark_all_read(current_user.id)
