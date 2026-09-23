import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.quick_replies.models import QuickReply
from app.modules.quick_replies.repository import QuickReplyRepository
from app.modules.quick_replies.schemas import QuickReplyCreateRequest, QuickReplyUpdateRequest


class QuickReplyService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = QuickReplyRepository(session, organization_id=organization_id)

    async def list_quick_replies(self, limit: int, offset: int) -> list[QuickReply]:
        return await self.repo.list(limit=limit, offset=offset)

    async def create_quick_reply(self, request: QuickReplyCreateRequest) -> QuickReply:
        quick_reply = await self.repo.create(
            QuickReply(
                organization_id=self.organization_id, title=request.title, content=request.content
            )
        )
        await self.session.commit()
        return quick_reply

    async def update_quick_reply(
        self, quick_reply_id: uuid.UUID, request: QuickReplyUpdateRequest
    ) -> QuickReply:
        quick_reply = await self._get_or_404(quick_reply_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(quick_reply, field, value)
        await self.repo.update(quick_reply)
        await self.session.commit()
        return quick_reply

    async def delete_quick_reply(self, quick_reply_id: uuid.UUID) -> None:
        quick_reply = await self._get_or_404(quick_reply_id)
        await self.repo.soft_delete(quick_reply)
        await self.session.commit()

    async def _get_or_404(self, quick_reply_id: uuid.UUID) -> QuickReply:
        quick_reply = await self.repo.get_by_id(quick_reply_id)
        if not quick_reply:
            raise NotFoundError("Quick reply not found.")
        return quick_reply
