import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.modules.customers.repository import CustomerRepository
from app.modules.notifications.service import NotificationService
from app.modules.tickets.models import Ticket, TicketComment
from app.modules.tickets.repository import TicketCommentRepository, TicketRepository
from app.modules.tickets.schemas import TicketCreateRequest, TicketUpdateRequest
from app.modules.webhooks.service import WebhookService


class TicketService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = TicketRepository(session, organization_id=organization_id)
        self.comment_repo = TicketCommentRepository(session, organization_id=organization_id)
        self.customer_repo = CustomerRepository(session, organization_id=organization_id)
        self.webhook_service = WebhookService(session, organization_id)
        self.notification_service = NotificationService(session, organization_id)

    async def create_ticket(
        self, reporter_user_id: uuid.UUID, request: TicketCreateRequest
    ) -> Ticket:
        # Validates the customer belongs to this org before creating —
        # otherwise an agent could create a ticket against another
        # tenant's customer just by guessing a UUID.
        customer = await self.customer_repo.get_by_id(request.customer_id)
        if not customer:
            raise NotFoundError("Customer not found.")

        ticket = await self.repo.create(
            Ticket(
                organization_id=self.organization_id,
                customer_id=request.customer_id,
                conversation_id=request.conversation_id,
                department_id=request.department_id,
                assigned_agent_id=request.assigned_agent_id,
                created_by_user_id=reporter_user_id,
                subject=request.subject,
                description=request.description,
                priority=request.priority,
            )
        )
        if request.assigned_agent_id:
            await self.notification_service.notify_users(
                [request.assigned_agent_id], "ticket_assigned", {"ticket_id": str(ticket.id)}
            )
        await self.session.commit()
        await self.webhook_service.dispatch("ticket.created", {"ticket_id": str(ticket.id)})
        return ticket

    async def list_tickets(
        self,
        status: str | None,
        priority: str | None,
        assigned_agent_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[Ticket]:
        return await self.repo.list_filtered(status, priority, assigned_agent_id, limit, offset)

    async def get_ticket_detail(self, ticket_id: uuid.UUID) -> tuple[Ticket, list[TicketComment]]:
        ticket = await self._get_or_404(ticket_id)
        comments = await self.comment_repo.list_by_ticket(ticket_id)
        return ticket, comments

    async def update_ticket(
        self,
        ticket_id: uuid.UUID,
        current_user_id: uuid.UUID,
        current_user_roles: list[str],
        request: TicketUpdateRequest,
    ) -> Ticket:
        ticket = await self._get_or_404(ticket_id)

        is_privileged = bool({"org_admin", "team_manager"} & set(current_user_roles))
        is_owner_or_unassigned = ticket.assigned_agent_id in (None, current_user_id)
        if not is_privileged and not is_owner_or_unassigned:
            raise ForbiddenError("You can only modify tickets assigned to you.")

        update_data = request.model_dump(exclude_unset=True)
        previous_assignee = ticket.assigned_agent_id
        for field, value in update_data.items():
            setattr(ticket, field, value)
        if update_data.get("status") in ("resolved", "closed") and not ticket.resolved_at:
            ticket.resolved_at = datetime.now(timezone.utc)
        elif update_data.get("status") in ("open", "pending"):
            ticket.resolved_at = None

        new_assignee = update_data.get("assigned_agent_id")
        if "assigned_agent_id" in update_data and new_assignee and new_assignee != previous_assignee:
            await self.notification_service.notify_users(
                [new_assignee], "ticket_assigned", {"ticket_id": str(ticket.id)}
            )

        await self.repo.update(ticket)
        await self.session.commit()
        await self.webhook_service.dispatch("ticket.updated", {"ticket_id": str(ticket.id)})
        return ticket

    async def add_comment(
        self, ticket_id: uuid.UUID, author_user_id: uuid.UUID, text: str
    ) -> TicketComment:
        await self._get_or_404(ticket_id)
        comment = await self.comment_repo.create(
            TicketComment(
                organization_id=self.organization_id,
                ticket_id=ticket_id,
                author_user_id=author_user_id,
                text=text,
            )
        )
        await self.session.commit()
        return comment

    async def _get_or_404(self, ticket_id: uuid.UUID) -> Ticket:
        ticket = await self.repo.get_by_id(ticket_id)
        if not ticket:
            raise NotFoundError("Ticket not found.")
        return ticket
