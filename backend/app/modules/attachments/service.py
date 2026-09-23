import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenError, ValidationError
from app.modules.attachments.models import Attachment
from app.modules.attachments.repository import AttachmentRepository
from app.modules.attachments.storage import storage_backend
from app.modules.conversations.models import Message
from app.modules.conversations.repository import ConversationRepository, MessageRepository
from app.modules.customers.repository import CustomerRepository
from app.websockets.pubsub import publish_to_conversation, publish_to_org_agents


class AttachmentService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.conversation_repo = ConversationRepository(session, organization_id=organization_id)
        self.message_repo = MessageRepository(session, organization_id=organization_id)
        self.attachment_repo = AttachmentRepository(session, organization_id=organization_id)
        self.customer_repo = CustomerRepository(session, organization_id=organization_id)

    async def upload_customer_attachment(
        self,
        redis: Redis,
        conversation_id: uuid.UUID,
        external_id: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> Attachment:
        conversation = await self._get_conversation_or_404(conversation_id)
        customer = await self.customer_repo.get_by_external_id(self.organization_id, external_id)
        if not customer or customer.id != conversation.customer_id:
            raise ForbiddenError("This conversation does not belong to that customer.")

        return await self._store_and_attach(
            redis, conversation, "customer", customer.id, filename, content_type, content
        )

    async def upload_agent_attachment(
        self,
        redis: Redis,
        conversation_id: uuid.UUID,
        agent_user_id: uuid.UUID,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> Attachment:
        conversation = await self._get_conversation_or_404(conversation_id)
        return await self._store_and_attach(
            redis, conversation, "agent", agent_user_id, filename, content_type, content
        )

    async def get_attachment_for_download(self, attachment_id: uuid.UUID) -> tuple[Attachment, bytes]:
        attachment = await self.attachment_repo.get_by_id(attachment_id)
        if not attachment:
            from app.core.exceptions import NotFoundError

            raise NotFoundError("Attachment not found.")
        content = await storage_backend.read(attachment.storage_path)
        return attachment, content

    async def get_attachment_for_public_download(
        self, attachment_id: uuid.UUID, external_id: str
    ) -> tuple[Attachment, bytes]:
        from app.core.exceptions import NotFoundError

        attachment = await self.attachment_repo.get_by_id(attachment_id)
        if not attachment:
            raise NotFoundError("Attachment not found.")

        message = await self.message_repo.get_by_id(attachment.message_id)
        if not message:
            raise NotFoundError("Attachment not found.")
        conversation = await self.conversation_repo.get_by_id(message.conversation_id)
        customer = await self.customer_repo.get_by_external_id(self.organization_id, external_id)
        if not conversation or not customer or customer.id != conversation.customer_id:
            raise ForbiddenError("This attachment does not belong to that customer.")

        content = await storage_backend.read(attachment.storage_path)
        return attachment, content

    # ---------- internals ----------

    async def _get_conversation_or_404(self, conversation_id: uuid.UUID):
        from app.core.exceptions import NotFoundError

        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def _store_and_attach(
        self,
        redis: Redis,
        conversation,
        sender_type: str,
        sender_id: uuid.UUID,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> Attachment:
        if len(content) == 0:
            raise ValidationError("Uploaded file is empty.")
        if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise ValidationError(
                f"File exceeds the {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB limit."
            )

        storage_path = await storage_backend.save(self.organization_id, filename, content)

        message = await self.message_repo.create(
            Message(
                organization_id=self.organization_id,
                conversation_id=conversation.id,
                sender_type=sender_type,
                sender_id=sender_id,
                content=f"[attachment: {filename}]",
            )
        )
        attachment = await self.attachment_repo.create(
            Attachment(
                organization_id=self.organization_id,
                message_id=message.id,
                original_filename=filename,
                content_type=content_type,
                size_bytes=len(content),
                storage_path=storage_path,
            )
        )

        from datetime import datetime, timezone

        conversation.last_message_at = datetime.now(timezone.utc)
        await self.conversation_repo.update(conversation)
        await self.session.commit()

        payload = {
            "type": "new_message",
            "conversation_id": str(conversation.id),
            "message": {
                "id": str(message.id),
                "sender_type": message.sender_type,
                "sender_id": str(message.sender_id) if message.sender_id else None,
                "content": message.content,
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "attachment": {
                    "id": str(attachment.id),
                    "original_filename": attachment.original_filename,
                    "content_type": attachment.content_type,
                    "size_bytes": attachment.size_bytes,
                },
            },
        }
        await publish_to_conversation(redis, conversation.id, payload)
        await publish_to_org_agents(redis, conversation.organization_id, payload)

        return attachment
