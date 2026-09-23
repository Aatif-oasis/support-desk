import uuid

from sqlalchemy import select

from app.modules.tickets.models import Ticket, TicketComment
from app.shared.base_repository import BaseRepository


class TicketRepository(BaseRepository[Ticket]):
    model = Ticket

    async def list_filtered(
        self,
        status: str | None,
        priority: str | None,
        assigned_agent_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[Ticket]:
        query = self._base_query().order_by(Ticket.created_at.desc())
        if status:
            query = query.where(Ticket.status == status)
        if priority:
            query = query.where(Ticket.priority == priority)
        if assigned_agent_id:
            query = query.where(Ticket.assigned_agent_id == assigned_agent_id)
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class TicketCommentRepository(BaseRepository[TicketComment]):
    model = TicketComment

    async def list_by_ticket(self, ticket_id: uuid.UUID) -> list[TicketComment]:
        query = (
            self._base_query()
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
