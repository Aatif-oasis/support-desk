import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import NotFoundError
from app.modules.webhooks.models import WebhookDelivery, WebhookSubscription
from app.modules.webhooks.repository import WebhookDeliveryRepository, WebhookSubscriptionRepository
from app.modules.webhooks.schemas import (
    WebhookSubscriptionCreateRequest,
    WebhookSubscriptionUpdateRequest,
)

logger = logging.getLogger(__name__)

_DELIVERY_TIMEOUT_SECONDS = 5.0
_RETRY_BACKOFF_SECONDS = [2, 10, 30]

# asyncio only keeps a weak reference to running tasks; without this set a
# delivery can be collected before it finishes.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


async def _post_once(
    url: str, secret: str, event: str, payload: dict
) -> tuple[int | None, str | None]:
    """Returns (response_status, error). Never raises."""
    body = json.dumps({"event": event, "data": payload}, default=str)
    try:
        async with httpx.AsyncClient(timeout=_DELIVERY_TIMEOUT_SECONDS) as http_client:
            response = await http_client.post(
                url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Oasis-Signature": _sign(secret, body),
                    "X-Oasis-Event": event,
                },
            )
            return response.status_code, None
    except httpx.HTTPError as exc:
        return None, str(exc)


async def _deliver_in_background(
    organization_id: uuid.UUID,
    event: str,
    payload: dict,
    targets: list[tuple[uuid.UUID, str, str]],
) -> None:
    """
    Runs after the triggering request has already returned. Retries a
    handful of times with a widening gap, because the common failure is a
    receiver that is briefly restarting rather than permanently gone — and
    losing a chat.created event means that customer never reaches the CRM
    at all.
    """
    for subscription_id, url, secret in targets:
        status_code: int | None = None
        error: str | None = None

        for attempt in range(settings.WEBHOOK_MAX_ATTEMPTS):
            status_code, error = await _post_once(url, secret, event, payload)
            if status_code is not None and 200 <= status_code < 300:
                error = None
                break
            if error is None:
                error = f"Receiver responded with HTTP {status_code}"
            if attempt < settings.WEBHOOK_MAX_ATTEMPTS - 1:
                delay = _RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)]
                await asyncio.sleep(delay)

        try:
            async with AsyncSessionLocal() as session:
                session.add(
                    WebhookDelivery(
                        organization_id=organization_id,
                        subscription_id=subscription_id,
                        event=event,
                        payload=payload,
                        response_status=status_code,
                        error=error,
                        delivered_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
        except Exception:  # noqa: BLE001 - logging a delivery must never crash the app
            logger.exception("Failed to record webhook delivery for %s", event)


class WebhookService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.sub_repo = WebhookSubscriptionRepository(session, organization_id=organization_id)
        self.delivery_repo = WebhookDeliveryRepository(session, organization_id=organization_id)

    # ---------- Subscription CRUD ----------

    async def list_subscriptions(self) -> list[WebhookSubscription]:
        return await self.sub_repo.list(limit=200, offset=0)

    async def create_subscription(
        self, request: WebhookSubscriptionCreateRequest
    ) -> WebhookSubscription:
        subscription = await self.sub_repo.create(
            WebhookSubscription(
                organization_id=self.organization_id,
                url=request.url,
                events=request.events,
                secret=secrets.token_urlsafe(32),
            )
        )
        await self.session.commit()
        return subscription

    async def update_subscription(
        self, subscription_id: uuid.UUID, request: WebhookSubscriptionUpdateRequest
    ) -> WebhookSubscription:
        subscription = await self._get_or_404(subscription_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(subscription, field, value)
        await self.sub_repo.update(subscription)
        await self.session.commit()
        return subscription

    async def delete_subscription(self, subscription_id: uuid.UUID) -> None:
        subscription = await self._get_or_404(subscription_id)
        await self.sub_repo.soft_delete(subscription)
        await self.session.commit()

    async def list_deliveries(self, subscription_id: uuid.UUID) -> list[WebhookDelivery]:
        await self._get_or_404(subscription_id)
        query_repo = self.delivery_repo
        all_deliveries = await query_repo.list(limit=200, offset=0)
        return [d for d in all_deliveries if d.subscription_id == subscription_id]

    # ---------- Dispatch engine ----------

    async def dispatch(self, event: str, payload: dict) -> None:
        """
        A webhook receiver being slow or down must never block or fail the
        operation that triggered it — a customer sending a message should
        not wait on someone's CRM endpoint.

        Two modes, controlled by WEBHOOK_ASYNC_DELIVERY:

        - async (recommended for real deployments): the HTTP calls and
          retries run in a background task with their own DB session, so
          the customer's request returns immediately.
        - inline (the default, and what the existing test suite expects):
          delivery happens before this returns, single attempt.
        """
        subscriptions = await self.sub_repo.list_active()
        targets = [
            (s.id, s.url, s.secret) for s in subscriptions if event in (s.events or [])
        ]
        if not targets:
            return

        if settings.WEBHOOK_ASYNC_DELIVERY:
            task = asyncio.create_task(
                _deliver_in_background(self.organization_id, event, payload, targets)
            )
            # Hold a reference so the task isn't garbage-collected mid-flight.
            _BACKGROUND_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_TASKS.discard)
            return

        for subscription_id, url, secret in targets:
            status_code, error = await _post_once(url, secret, event, payload)
            await self.delivery_repo.create(
                WebhookDelivery(
                    organization_id=self.organization_id,
                    subscription_id=subscription_id,
                    event=event,
                    payload=payload,
                    response_status=status_code,
                    error=error,
                    delivered_at=datetime.now(timezone.utc),
                )
            )
            await self.session.commit()

    async def _get_or_404(self, subscription_id: uuid.UUID) -> WebhookSubscription:
        subscription = await self.sub_repo.get_by_id(subscription_id)
        if not subscription:
            raise NotFoundError("Webhook subscription not found.")
        return subscription
