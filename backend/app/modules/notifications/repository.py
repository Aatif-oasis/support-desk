import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from app.modules.notifications.models import Notification
from app.shared.base_repository import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def list_for_user(
        self, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
    ) -> list[Notification]:
        query = self._base_query().where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def unread_count(self, user_id: uuid.UUID) -> int:
        query = select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
            Notification.deleted_at.is_(None),
        )
        result = await self.session.execute(query)
        return result.scalar_one()

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(read_at=datetime.now(timezone.utc))
        )
        await self.session.flush()

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(timezone.utc))
        )
        await self.session.flush()

    async def bulk_create_for_users(
        self, organization_id: uuid.UUID, user_ids: list[uuid.UUID], type_: str, payload: dict
    ) -> None:
        for uid in user_ids:
            self.session.add(
                Notification(organization_id=organization_id, user_id=uid, type=type_, payload=payload)
            )
        await self.session.flush()
