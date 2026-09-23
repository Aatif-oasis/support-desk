import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.notifications.repository import NotificationRepository


class NotificationService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = NotificationRepository(session, organization_id=organization_id)

    async def list_notifications(
        self, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
    ) -> list[Notification]:
        return await self.repo.list_for_user(user_id, unread_only, limit, offset)

    async def unread_count(self, user_id: uuid.UUID) -> int:
        return await self.repo.unread_count(user_id)

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.repo.mark_read(notification_id, user_id)
        await self.session.commit()

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self.repo.mark_all_read(user_id)
        await self.session.commit()

    async def notify_users(self, user_ids: list[uuid.UUID], type_: str, payload: dict) -> None:
        """
        Called by OTHER modules (Conversations, Tickets) to persist a
        notification — separate from the ephemeral WebSocket push, which
        those modules still send directly via app.websockets.pubsub. This
        does not commit; the caller's existing transaction commits it,
        since it's always invoked from inside another service's write.
        """
        if not user_ids:
            return
        await self.repo.bulk_create_for_users(self.organization_id, user_ids, type_, payload)
