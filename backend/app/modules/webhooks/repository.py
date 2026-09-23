from app.modules.webhooks.models import WebhookDelivery, WebhookSubscription
from app.shared.base_repository import BaseRepository


class WebhookSubscriptionRepository(BaseRepository[WebhookSubscription]):
    model = WebhookSubscription

    async def list_active(self) -> list[WebhookSubscription]:
        query = self._base_query().where(WebhookSubscription.is_active.is_(True))
        result = await self.session.execute(query)
        return list(result.scalars().all())


class WebhookDeliveryRepository(BaseRepository[WebhookDelivery]):
    model = WebhookDelivery
