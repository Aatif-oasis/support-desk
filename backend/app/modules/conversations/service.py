import uuid
from collections.abc import Iterable
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.modules.conversations.models import Conversation, ConversationNote, Message, Tag
from app.modules.conversations.repository import (
    ConversationNoteRepository,
    ConversationRepository,
    MessageRepository,
    TagRepository,
)
from app.modules.conversations.schemas import ConversationUpdateRequest
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.users.repository import UserRepository
from app.modules.automation.engine import collect_actions
from app.modules.automation.repository import AutomationRuleRepository
from app.modules.notifications.service import NotificationService
from app.modules.webhooks.service import WebhookService
from app.modules.users.repository import UserRepository
from app.websockets.pubsub import publish_to_conversation, publish_to_org_agents


class ConversationService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.conversation_repo = ConversationRepository(session, organization_id=organization_id)
        self.message_repo = MessageRepository(session, organization_id=organization_id)
        self.customer_repo = CustomerRepository(session, organization_id=organization_id)
        self.note_repo = ConversationNoteRepository(session, organization_id=organization_id)
        self.tag_repo = TagRepository(session, organization_id=organization_id)
        self.user_repo = UserRepository(session, organization_id=organization_id)
        self.notification_service = NotificationService(session, organization_id)
        self.automation_repo = AutomationRuleRepository(session, organization_id=organization_id)
        self.webhook_service = WebhookService(session, organization_id)

    # ---------- Public (widget-facing) ----------

    async def start_conversation(
        self,
        redis: Redis,
        external_id: str,
        initial_message: str,
        full_name: str,
        phone: str,
    ) -> tuple[Conversation, Message]:
        customer = await self.customer_repo.get_by_external_id(self.organization_id, external_id)
        if not customer:
            # Widgets are expected to call /identify first, but don't hard-fail
            # a chat just because that call was skipped — create the customer
            # record here instead, using the full_name/phone this endpoint
            # itself now requires (see ConversationStartRequest) so a
            # conversation can never exist without them.
            from app.modules.customers.models import Customer

            customer = await self.customer_repo.create(
                Customer(
                    organization_id=self.organization_id,
                    external_id=external_id,
                    full_name=full_name,
                    phone=phone,
                )
            )
        else:
            # Progressive identification, same rule as CustomerService.identify:
            # never blank out data that's already there, but backfill if this
            # customer somehow doesn't have it yet (e.g. /identify was never
            # called, or was called before these fields existed).
            changed = False
            if not customer.full_name:
                customer.full_name = full_name
                changed = True
            if not customer.phone:
                customer.phone = phone
                changed = True
            if changed:
                await self.customer_repo.update(customer)

        now = datetime.now(timezone.utc)
        conversation = await self.conversation_repo.create(
            Conversation(
                organization_id=self.organization_id,
                customer_id=customer.id,
                status="open",
                started_at=now,
                last_message_at=now,
            )
        )
        message = await self.message_repo.create(
            Message(
                organization_id=self.organization_id,
                conversation_id=conversation.id,
                sender_type="customer",
                sender_id=customer.id,
                content=initial_message,
            )
        )

        agent_ids = await self.user_repo.list_agent_user_ids()
        await self.notification_service.notify_users(
            agent_ids,
            "new_conversation",
            {"conversation_id": str(conversation.id), "preview": initial_message[:200]},
        )
        await self.session.commit()

        await self.webhook_service.dispatch(
            "chat.created", {"conversation_id": str(conversation.id), "customer_id": str(customer.id)}
        )
        await self.webhook_service.dispatch(
            "message.received",
            {"conversation_id": str(conversation.id), "message_id": str(message.id), "content": initial_message},
        )
        await self._run_automation(redis, conversation, "conversation_created", initial_message)

        await publish_to_org_agents(
            redis,
            self.organization_id,
            {
                "type": "new_conversation",
                "conversation_id": str(conversation.id),
                "customer_name": customer.full_name,
                "preview": initial_message[:200],
            },
        )
        return conversation, message

    async def add_customer_message(
        self, redis: Redis, conversation_id: uuid.UUID, external_id: str, content: str
    ) -> Message:
        conversation = await self._get_conversation_or_404(conversation_id)
        customer = await self.customer_repo.get_by_external_id(self.organization_id, external_id)
        if not customer or customer.id != conversation.customer_id:
            raise ForbiddenError("This conversation does not belong to that customer.")

        message = await self._create_message_and_publish(
            redis, conversation, sender_type="customer", sender_id=customer.id, content=content
        )
        await self._run_automation(redis, conversation, "message_received", content)
        return message

    async def get_public_conversation(
        self, conversation_id: uuid.UUID, external_id: str
    ) -> tuple[Conversation, list[Message]]:
        """
        History replay for the widget after a page refresh. Ownership is
        re-checked against external_id every time — the conversation id
        alone is not a credential, so knowing one must not be enough to
        read someone else's chat.
        """
        conversation = await self._get_conversation_or_404(conversation_id)
        customer = await self.customer_repo.get_by_external_id(self.organization_id, external_id)
        if not customer or customer.id != conversation.customer_id:
            raise ForbiddenError("This conversation does not belong to that visitor.")
        messages = await self.message_repo.list_by_conversation(conversation_id)
        return conversation, messages

    # ---------- Customer lookup (for display) ----------

    async def customers_by_id(
        self, conversations: Iterable[Conversation]
    ) -> dict[uuid.UUID, Customer]:
        """
        One query for every customer referenced by a page of conversations,
        rather than a per-row lookup — this is what lets the API return
        customer_name/customer_phone without an N+1.
        """
        customer_ids = {c.customer_id for c in conversations}
        if not customer_ids:
            return {}
        query = select(Customer).where(
            Customer.organization_id == self.organization_id,
            Customer.id.in_(customer_ids),
            Customer.deleted_at.is_(None),
        )
        result = await self.session.execute(query)
        return {customer.id: customer for customer in result.scalars().all()}

    async def get_customer_for(self, conversation: Conversation) -> Customer | None:
        return (await self.customers_by_id([conversation])).get(conversation.customer_id)

    # ---------- Agent-facing ----------

    # ---------- Access control ----------

    # An agent works only their own queue. Admins and team managers are
    # supervisors, so they can read and step into anything in the org.
    PRIVILEGED_ROLES = {"org_admin", "team_manager"}

    @classmethod
    def is_privileged(cls, roles: list[str] | None) -> bool:
        return bool(cls.PRIVILEGED_ROLES & set(roles or []))

    def assert_can_access(
        self,
        conversation: Conversation,
        current_user_id: uuid.UUID | None,
        current_user_roles: list[str] | None,
    ) -> None:
        """
        Guards reading and replying, not just assignment changes. Without
        this an agent could open any conversation id in the org — including
        one already being handled by a colleague — and reply into it, which
        the customer would see as two different people answering.

        Unassigned conversations stay open to everyone: that is the shared
        queue, and claiming one is how an agent picks up work.
        """
        if self.is_privileged(current_user_roles):
            return
        if conversation.assigned_agent_id in (None, current_user_id):
            return
        raise ForbiddenError("This conversation is assigned to another agent.")

    async def list_conversations(
        self,
        status: str | None,
        limit: int,
        offset: int,
        current_user_id: uuid.UUID | None = None,
        current_user_roles: list[str] | None = None,
    ) -> list[Conversation]:
        """
        Every agent sees the whole board — who came in today, which chats
        are still unclaimed, and who is handling what. Visibility of the
        list is deliberately not restricted: an agent needs it to know
        whether a customer is already being helped.

        What stays protected is the content. Opening, reading and replying
        are guarded by assert_can_access, so seeing that a chat exists
        never means being able to read it.
        """
        return await self.conversation_repo.list_filtered(status, limit, offset)

    async def get_conversation_detail(self, conversation_id: uuid.UUID) -> tuple[Conversation, list[Message]]:
        conversation = await self._get_conversation_or_404(conversation_id)
        messages = await self.message_repo.list_by_conversation(conversation_id)
        return conversation, messages

    async def open_conversation_as_agent(
        self,
        redis: Redis,
        conversation_id: uuid.UUID,
        agent_user_id: uuid.UUID,
        current_user_roles: list[str] | None = None,
    ) -> tuple[Conversation, list[Message]]:
        """
        Agent-side "open" — distinct from get_conversation_detail because
        opening an unassigned conversation is itself an action: the first
        agent to click into it claims it, same as picking up a ringing
        phone. A conversation already assigned to a different agent is
        off-limits unless the caller is an admin or team manager.
        """
        conversation = await self._get_conversation_or_404(conversation_id)
        self.assert_can_access(conversation, agent_user_id, current_user_roles)

        # A supervisor looking into someone else's chat is announced to the
        # agents only — never written into the thread. The visitor has no
        # reason to know about the company's internal hierarchy, and being
        # told "an administrator is watching" would only alarm them.
        if (
            conversation.assigned_agent_id
            and conversation.assigned_agent_id != agent_user_id
            and self.is_privileged(current_user_roles)
        ):
            await publish_to_org_agents(
                redis,
                self.organization_id,
                {
                    "type": "supervisor_viewing",
                    "conversation_id": str(conversation.id),
                    "viewer_id": str(agent_user_id),
                    "viewer_name": await self._agent_name(agent_user_id),
                },
            )

        if conversation.assigned_agent_id is None:
            conversation.assigned_agent_id = agent_user_id
            await self.conversation_repo.update(conversation)
            await self.session.commit()

            # The visitor has been staring at a waiting screen. An opening
            # line from a named person is the most reassuring thing this
            # system can say — and it is sent as the agent, in their own
            # bubble, because a greeting is someone speaking, not the room
            # announcing itself the way a transfer notice is.
            if settings.AGENT_JOIN_GREETING:
                await self._create_message_and_publish(
                    redis,
                    conversation,
                    sender_type="agent",
                    sender_id=agent_user_id,
                    content=settings.AGENT_JOIN_GREETING.format(
                        agent=await self._agent_name(agent_user_id)
                    ),
                )

            # Org-wide broadcast so every dashboard's conversation list
            # drops the "unassigned" indicator immediately, not just for
            # the agent who opened it.
            await publish_to_org_agents(
                redis,
                self.organization_id,
                {
                    "type": "conversation_transferred",
                    "conversation_id": str(conversation.id),
                    "assigned_agent_id": str(agent_user_id),
                    "previous_agent_id": None,
                },
            )

        messages = await self.message_repo.list_by_conversation(conversation_id)
        return conversation, messages

    async def add_agent_message(
        self,
        redis: Redis,
        conversation_id: uuid.UUID,
        agent_user_id: uuid.UUID,
        content: str,
        current_user_roles: list[str] | None = None,
    ) -> Message:
        conversation = await self._get_conversation_or_404(conversation_id)
        # Reading was guarded above; writing needs the same guard, or an
        # agent could still post into a colleague's chat by calling the API
        # directly even after the UI stops showing it to them.
        self.assert_can_access(conversation, agent_user_id, current_user_roles)
        return await self._create_message_and_publish(
            redis, conversation, sender_type="agent", sender_id=agent_user_id, content=content
        )

    # ---------- Read receipts ----------

    async def mark_read_by_agent(
        self,
        redis: Redis,
        conversation_id: uuid.UUID,
        agent_user_id: uuid.UUID,
        current_user_roles: list[str] | None = None,
    ) -> Conversation:
        """
        The agent has the chat open, so everything in it has been seen.
        The customer's widget is told over the socket, which is the whole
        point: a visitor who can see their message was read stops
        wondering whether it arrived at all.
        """
        conversation = await self._get_conversation_or_404(conversation_id)
        self.assert_can_access(conversation, agent_user_id, current_user_roles)

        conversation.agent_last_read_at = datetime.now(timezone.utc)
        await self.conversation_repo.update(conversation)
        await self.session.commit()

        await publish_to_conversation(
            redis,
            conversation.id,
            {
                "type": "read_receipt",
                "conversation_id": str(conversation.id),
                "by": "agent",
                "at": conversation.agent_last_read_at.isoformat(),
            },
        )
        return conversation

    async def mark_read_by_customer(
        self, redis: Redis, conversation_id: uuid.UUID, external_id: str
    ) -> Conversation:
        """Same, from the visitor's side. Ownership re-checked, as always."""
        conversation = await self._get_conversation_or_404(conversation_id)
        customer = await self.customer_repo.get_by_external_id(self.organization_id, external_id)
        if not customer or customer.id != conversation.customer_id:
            raise ForbiddenError("This conversation does not belong to that visitor.")

        conversation.customer_last_read_at = datetime.now(timezone.utc)
        await self.conversation_repo.update(conversation)
        await self.session.commit()

        payload = {
            "type": "read_receipt",
            "conversation_id": str(conversation.id),
            "by": "customer",
            "at": conversation.customer_last_read_at.isoformat(),
        }
        # Agents watch two channels: the conversation itself when they have
        # it open, and the org-wide one for their inbox. Both get it.
        await publish_to_conversation(redis, conversation.id, payload)
        await publish_to_org_agents(redis, self.organization_id, payload)
        return conversation

    # ---------- System announcements ----------

    async def _agent_name(self, user_id: uuid.UUID | None) -> str:
        if not user_id:
            return "Someone"
        user = await UserRepository(self.session).get_by_id(user_id)
        return user.full_name if user else "An agent"

    async def add_system_message(
        self, redis: Redis, conversation: Conversation, text: str
    ) -> Message:
        """
        A line in the thread that neither side typed — "Rahul joined the
        chat", "Rahul transferred this chat to Priya".

        Stored as a real message rather than pushed as a transient event,
        for two reasons: the visitor sees it live *and* still sees it
        after a refresh, and an agent reading the history a week later can
        tell who handled what and when.
        """
        return await self._create_message_and_publish(
            redis, conversation, sender_type="system", sender_id=None, content=text
        )

    async def add_integration_message(
        self,
        redis: Redis,
        conversation_id: uuid.UUID,
        content: str,
        agent_user_id: uuid.UUID | None = None,
    ) -> Message:
        """
        A reply sent by an external system (CRM/ERP) over the API-key API
        rather than by a logged-in agent in the dashboard. It is stored as
        sender_type='agent' so the customer's widget renders it exactly like
        any other agent reply; sender_id is left NULL when the CRM doesn't
        map its operator to a Chat Support user, which the Message model
        already allows.
        """
        conversation = await self._get_conversation_or_404(conversation_id)
        return await self._create_message_and_publish(
            redis, conversation, sender_type="agent", sender_id=agent_user_id, content=content
        )

    async def update_conversation(
        self,
        redis: Redis,
        conversation_id: uuid.UUID,
        current_user_id: uuid.UUID,
        current_user_roles: list[str],
        request: ConversationUpdateRequest,
    ) -> Conversation:
        conversation = await self._get_conversation_or_404(conversation_id)

        is_privileged = bool({"org_admin", "team_manager"} & set(current_user_roles))
        is_owner_or_unassigned = conversation.assigned_agent_id in (None, current_user_id)
        if not is_privileged and not is_owner_or_unassigned:
            raise ForbiddenError("You can only modify conversations assigned to you.")

        update_data = request.model_dump(exclude_unset=True)

        # Transferring to someone who can't sign in would strand the
        # conversation exactly the way a departing agent's open chats do:
        # visible to everyone, openable by nobody. Check before, not after.
        target_agent_id = update_data.get("assigned_agent_id")
        if target_agent_id:
            target = await UserRepository(self.session).get_by_id(target_agent_id)
            if not target or target.organization_id != self.organization_id:
                raise NotFoundError("That agent is not part of this workspace.")
            if target.status == "suspended":
                raise ForbiddenError("That account is suspended and cannot take conversations.")

        previous_assignee = conversation.assigned_agent_id
        for field, value in update_data.items():
            setattr(conversation, field, value)
        if update_data.get("status") == "closed":
            conversation.closed_at = datetime.now(timezone.utc)

        new_assignee = update_data.get("assigned_agent_id")
        if "assigned_agent_id" in update_data and new_assignee != previous_assignee and new_assignee:
            await self.notification_service.notify_users(
                [new_assignee],
                "conversation_transferred",
                {"conversation_id": str(conversation.id)},
            )

        await self.conversation_repo.update(conversation)
        await self.session.commit()

        if update_data.get("status") == "closed":
            await self.webhook_service.dispatch(
                "chat.closed", {"conversation_id": str(conversation.id)}
            )

        if "assigned_agent_id" in update_data and new_assignee != previous_assignee:
            # Said out loud in the thread, so the visitor isn't left
            # wondering why the name above the chat suddenly changed, and
            # the receiving agent can see the handover in context.
            if new_assignee:
                from_name = await self._agent_name(previous_assignee)
                to_name = await self._agent_name(new_assignee)
                text = (
                    f"{to_name} joined the chat"
                    if not previous_assignee
                    else f"{from_name} transferred this chat to {to_name}"
                )
            else:
                text = "This chat was returned to the queue"
            await self.add_system_message(redis, conversation, text)

            # Closes the "no transfer notification" gap: every agent's
            # dashboard gets pushed a lightweight alert with who the new
            # assignee is, so the frontend can highlight it for that agent
            # specifically without needing a per-agent WebSocket channel.
            await publish_to_org_agents(
                redis,
                self.organization_id,
                {
                    "type": "conversation_transferred",
                    "conversation_id": str(conversation.id),
                    "assigned_agent_id": str(new_assignee) if new_assignee else None,
                    "previous_agent_id": str(previous_assignee) if previous_assignee else None,
                },
            )
        return conversation

    async def add_note(
        self,
        conversation_id: uuid.UUID,
        author_user_id: uuid.UUID,
        text: str,
        current_user_roles: list[str] | None = None,
    ) -> ConversationNote:
        conversation = await self._get_conversation_or_404(conversation_id)  # 404s if wrong org
        self.assert_can_access(conversation, author_user_id, current_user_roles)
        note = await self.note_repo.create(
            ConversationNote(
                organization_id=self.organization_id,
                conversation_id=conversation_id,
                author_user_id=author_user_id,
                text=text,
            )
        )
        await self.session.commit()
        return note

    async def list_notes(
        self,
        conversation_id: uuid.UUID,
        current_user_id: uuid.UUID | None = None,
        current_user_roles: list[str] | None = None,
    ) -> list[ConversationNote]:
        conversation = await self._get_conversation_or_404(conversation_id)
        # Internal notes are agents talking about a customer among
        # themselves — the most sensitive text in the system, so they get
        # the same guard as the conversation itself.
        self.assert_can_access(conversation, current_user_id, current_user_roles)
        return await self.note_repo.list_by_conversation(conversation_id)

    # ---------- Search ----------

    async def search_conversations(
        self,
        q: str,
        limit: int,
        offset: int,
        current_user_id: uuid.UUID | None = None,
        current_user_roles: list[str] | None = None,
    ) -> list[Conversation]:
        # Same rule as the list: finding a conversation is allowed, opening
        # someone else's is not.
        return await self.conversation_repo.search(q, limit, offset)

    # ---------- Tags ----------

    async def get_or_create_tag(self, name: str) -> Tag:
        tag = await self.tag_repo.get_by_name(name)
        if not tag:
            tag = await self.tag_repo.create(Tag(organization_id=self.organization_id, name=name))
            await self.session.commit()
        return tag

    async def assign_tag(self, conversation_id: uuid.UUID, tag_name: str) -> list[Tag]:
        await self._get_conversation_or_404(conversation_id)
        tag = await self.get_or_create_tag(tag_name)
        await self.conversation_repo.add_tag(conversation_id, tag.id)
        await self.session.commit()
        return await self.conversation_repo.list_tags(conversation_id)

    async def remove_tag(self, conversation_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        await self._get_conversation_or_404(conversation_id)
        await self.conversation_repo.remove_tag(conversation_id, tag_id)
        await self.session.commit()

    async def list_conversation_tags(self, conversation_id: uuid.UUID) -> list[Tag]:
        await self._get_conversation_or_404(conversation_id)
        return await self.conversation_repo.list_tags(conversation_id)

    # ---------- Export ----------

    async def export_conversation(self, conversation_id: uuid.UUID) -> dict:
        conversation, messages = await self.get_conversation_detail(conversation_id)
        return {
            "conversation_id": str(conversation.id),
            "status": conversation.status,
            "started_at": conversation.started_at.isoformat(),
            "closed_at": conversation.closed_at.isoformat() if conversation.closed_at else None,
            "messages": [
                {
                    "sender_type": m.sender_type,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }

    # ---------- Shared internals ----------

    async def _run_automation(
        self, redis: Redis, conversation: Conversation, trigger_event: str, message_content: str
    ) -> None:
        rules = await self.automation_repo.list_active_by_trigger(trigger_event)
        if not rules:
            return
        actions = collect_actions(rules, {"message_content": message_content})
        for action in actions:
            action_type = action.get("type")
            if action_type == "add_tag" and action.get("tag"):
                tag = await self.get_or_create_tag(action["tag"])
                await self.conversation_repo.add_tag(conversation.id, tag.id)
                await self.session.commit()
            elif action_type == "assign_agent" and action.get("agent_id"):
                conversation.assigned_agent_id = uuid.UUID(action["agent_id"])
                await self.conversation_repo.update(conversation)
                await self.session.commit()
            elif action_type == "auto_reply" and action.get("content"):
                await self._create_message_and_publish(
                    redis, conversation, sender_type="system", sender_id=None, content=action["content"]
                )

    async def _get_conversation_or_404(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def _create_message_and_publish(
        self,
        redis: Redis,
        conversation: Conversation,
        sender_type: str,
        sender_id: uuid.UUID | None,
        content: str,
    ) -> Message:
        message = await self.message_repo.create(
            Message(
                organization_id=self.organization_id,
                conversation_id=conversation.id,
                sender_type=sender_type,
                sender_id=sender_id,
                content=content,
            )
        )
        conversation.last_message_at = datetime.now(timezone.utc)
        await self.conversation_repo.update(conversation)
        await self.session.commit()

        if sender_type in ("customer", "agent"):
            event = "message.received" if sender_type == "customer" else "message.sent"
            await self.webhook_service.dispatch(
                event,
                {
                    "conversation_id": str(conversation.id),
                    "message_id": str(message.id),
                    "content": message.content,
                },
            )

        message_payload = {
            "type": "new_message",
            "conversation_id": str(conversation.id),
            "message": {
                "id": str(message.id),
                "sender_type": message.sender_type,
                "sender_id": str(message.sender_id) if message.sender_id else None,
                "content": message.content,
                "created_at": message.created_at.isoformat() if message.created_at else None,
            },
        }
        # Full message → anyone actively viewing this conversation (customer
        # widget or an agent with it open).
        await publish_to_conversation(redis, conversation.id, message_payload)
        # Lightweight echo → org-wide dashboard notification/unread badges,
        # regardless of whether any agent currently has this chat open.
        await publish_to_org_agents(redis, conversation.organization_id, message_payload)

        return message
