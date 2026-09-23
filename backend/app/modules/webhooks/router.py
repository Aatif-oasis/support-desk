import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.webhooks.schemas import (
    WebhookDeliveryResponse,
    WebhookSubscriptionCreateRequest,
    WebhookSubscriptionCreateResponse,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdateRequest,
)
from app.modules.webhooks.service import WebhookService

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


@router.get("", response_model=list[WebhookSubscriptionResponse])
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> list[WebhookSubscriptionResponse]:
    subs = await WebhookService(db, current_user.organization_id).list_subscriptions()
    return [WebhookSubscriptionResponse.model_validate(s) for s in subs]


@router.post("", response_model=WebhookSubscriptionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    request: WebhookSubscriptionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> WebhookSubscriptionCreateResponse:
    subscription = await WebhookService(db, current_user.organization_id).create_subscription(request)
    return WebhookSubscriptionCreateResponse(
        **WebhookSubscriptionResponse.model_validate(subscription).model_dump(),
        secret=subscription.secret,
    )


@router.patch("/{subscription_id}", response_model=WebhookSubscriptionResponse)
async def update_subscription(
    subscription_id: uuid.UUID,
    request: WebhookSubscriptionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> WebhookSubscriptionResponse:
    subscription = await WebhookService(db, current_user.organization_id).update_subscription(
        subscription_id, request
    )
    return WebhookSubscriptionResponse.model_validate(subscription)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> None:
    await WebhookService(db, current_user.organization_id).delete_subscription(subscription_id)


@router.get("/{subscription_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> list[WebhookDeliveryResponse]:
    deliveries = await WebhookService(db, current_user.organization_id).list_deliveries(
        subscription_id
    )
    return [WebhookDeliveryResponse.model_validate(d) for d in deliveries]
