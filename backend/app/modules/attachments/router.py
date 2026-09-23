import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.rate_limit import attachment_upload_rate_limit
from app.modules.attachments.schemas import AttachmentResponse
from app.modules.attachments.service import AttachmentService
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.customers.service import CustomerService

public_router = APIRouter(prefix="/api/v1/public/{org_slug}/conversations", tags=["Public — Widget"])
router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


@public_router.post("/{conversation_id}/attachments", response_model=AttachmentResponse, dependencies=[Depends(attachment_upload_rate_limit)])
async def upload_customer_attachment(
    org_slug: str,
    conversation_id: uuid.UUID,
    external_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AttachmentResponse:
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    content = await file.read()
    attachment = await AttachmentService(db, organization_id).upload_customer_attachment(
        redis, conversation_id, external_id, file.filename or "upload", file.content_type or "application/octet-stream", content
    )
    return AttachmentResponse.model_validate(attachment)


@public_router.get("/attachments/{attachment_id}/download")
async def download_attachment_public(
    org_slug: str,
    attachment_id: uuid.UUID,
    external_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    attachment, content = await AttachmentService(
        db, organization_id
    ).get_attachment_for_public_download(attachment_id, external_id)
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment.original_filename}"'},
    )


@router.post("/{conversation_id}/attachments", response_model=AttachmentResponse)
async def upload_agent_attachment(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> AttachmentResponse:
    content = await file.read()
    attachment = await AttachmentService(db, current_user.organization_id).upload_agent_attachment(
        redis,
        conversation_id,
        current_user.id,
        file.filename or "upload",
        file.content_type or "application/octet-stream",
        content,
    )
    return AttachmentResponse.model_validate(attachment)


@router.get("/attachments/{attachment_id}/download")
async def download_attachment_agent(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> Response:
    attachment, content = await AttachmentService(
        db, current_user.organization_id
    ).get_attachment_for_download(attachment_id)
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment.original_filename}"'},
    )
