import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.quick_replies.schemas import (
    QuickReplyCreateRequest,
    QuickReplyResponse,
    QuickReplyUpdateRequest,
)
from app.modules.quick_replies.service import QuickReplyService

router = APIRouter(prefix="/api/v1/quick-replies", tags=["Quick Replies"])


@router.get("", response_model=list[QuickReplyResponse])
async def list_quick_replies(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[QuickReplyResponse]:
    items = await QuickReplyService(db, current_user.organization_id).list_quick_replies(
        limit, offset
    )
    return [QuickReplyResponse.model_validate(i) for i in items]


@router.post("", response_model=QuickReplyResponse, status_code=status.HTTP_201_CREATED)
async def create_quick_reply(
    request: QuickReplyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> QuickReplyResponse:
    quick_reply = await QuickReplyService(db, current_user.organization_id).create_quick_reply(
        request
    )
    return QuickReplyResponse.model_validate(quick_reply)


@router.patch("/{quick_reply_id}", response_model=QuickReplyResponse)
async def update_quick_reply(
    quick_reply_id: uuid.UUID,
    request: QuickReplyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> QuickReplyResponse:
    quick_reply = await QuickReplyService(db, current_user.organization_id).update_quick_reply(
        quick_reply_id, request
    )
    return QuickReplyResponse.model_validate(quick_reply)


@router.delete("/{quick_reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quick_reply(
    quick_reply_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> None:
    await QuickReplyService(db, current_user.organization_id).delete_quick_reply(quick_reply_id)
