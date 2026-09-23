import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy import insert, or_, select

from app.modules.conversations.models import (
    Conversation,
    ConversationNote,
    Message,
    Tag,
    conversation_tags,
)
from app.modules.customers.models import Customer
from app.shared.base_repository import BaseRepository


class TagRepository(BaseRepository[Tag]):
    model = Tag

    async def get_by_name(self, name: str) -> Tag | None:
        query = self._base_query().where(Tag.name == name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class ConversationNoteRepository(BaseRepository[ConversationNote]):
    model = ConversationNote

    async def list_by_conversation(self, conversation_id: uuid.UUID) -> list[ConversationNote]:
        query = (
            self._base_query()
            .where(ConversationNote.conversation_id == conversation_id)
            .order_by(ConversationNote.created_at.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    async def list_filtered(
        self, status: str | None, limit: int, offset: int
    ) -> list[Conversation]:
        query = self._base_query().order_by(Conversation.last_message_at.desc().nullslast())
        if status:
            query = query.where(Conversation.status == status)
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def search(self, q: str, limit: int, offset: int) -> list[Conversation]:
        """ILIKE on message content or customer name/email — no search index needed at this scale."""
        pattern = f"%{q}%"
        query = (
            self._base_query()
            .join(Message, Message.conversation_id == Conversation.id)
            .join(Customer, Customer.id == Conversation.customer_id)
            .where(
                or_(
                    Message.content.ilike(pattern),
                    Customer.full_name.ilike(pattern),
                    Customer.email.ilike(pattern),
                )
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def add_tag(self, conversation_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        existing = await self.session.execute(
            select(conversation_tags).where(
                conversation_tags.c.conversation_id == conversation_id,
                conversation_tags.c.tag_id == tag_id,
            )
        )
        if existing.first() is None:
            await self.session.execute(
                insert(conversation_tags).values(conversation_id=conversation_id, tag_id=tag_id)
            )
            await self.session.flush()

    async def remove_tag(self, conversation_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        await self.session.execute(
            sql_delete(conversation_tags).where(
                conversation_tags.c.conversation_id == conversation_id,
                conversation_tags.c.tag_id == tag_id,
            )
        )
        await self.session.flush()

    async def list_tags(self, conversation_id: uuid.UUID) -> list[Tag]:
        query = (
            select(Tag)
            .join(conversation_tags, conversation_tags.c.tag_id == Tag.id)
            .where(conversation_tags.c.conversation_id == conversation_id, Tag.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def list_by_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        query = (
            self._base_query()
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
