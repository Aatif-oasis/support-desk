import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.conversations.service import ConversationService
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.tickets.schemas import (
    TicketCommentCreateRequest,
    TicketCommentResponse,
    TicketCreateRequest,
    TicketDetailResponse,
    TicketResponse,
    TicketUpdateRequest,
)
from app.modules.tickets.service import TicketService

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"])


async def _with_customer(db, organization_id, tickets):
    """
    Attaches customer names to a page of tickets in one query. Reuses the
    conversation service's lookup rather than growing a second copy of it.
    """
    responses = [TicketResponse.model_validate(t) for t in tickets]
    if not responses:
        return responses

    service = ConversationService(db, organization_id)
    # customers_by_id works off anything exposing .customer_id, which
    # tickets do.
    customers = await service.customers_by_id(tickets)
    for response in responses:
        customer = customers.get(response.customer_id)
        if customer:
            response.customer_name = customer.full_name
            response.customer_phone = customer.phone
    return responses


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    assigned_agent_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[TicketResponse]:
    tickets = await TicketService(db, current_user.organization_id).list_tickets(
        status_filter, priority, assigned_agent_id, limit, offset
    )
    return await _with_customer(db, current_user.organization_id, tickets)


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request: TicketCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> TicketResponse:
    ticket = await TicketService(db, current_user.organization_id).create_ticket(
        current_user.id, request
    )
    return (await _with_customer(db, current_user.organization_id, [ticket]))[0]


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> TicketDetailResponse:
    ticket, comments = await TicketService(db, current_user.organization_id).get_ticket_detail(
        ticket_id
    )
    enriched = (await _with_customer(db, current_user.organization_id, [ticket]))[0]
    return TicketDetailResponse(
        **enriched.model_dump(),
        comments=[TicketCommentResponse.model_validate(c) for c in comments],
    )


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: uuid.UUID,
    request: TicketUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> TicketResponse:
    ticket = await TicketService(db, current_user.organization_id).update_ticket(
        ticket_id, current_user.id, current_user.roles, request
    )
    return (await _with_customer(db, current_user.organization_id, [ticket]))[0]


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_comment(
    ticket_id: uuid.UUID,
    request: TicketCommentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> TicketCommentResponse:
    comment = await TicketService(db, current_user.organization_id).add_comment(
        ticket_id, current_user.id, request.text
    )
    return TicketCommentResponse.model_validate(comment)


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentResponse])
async def list_ticket_comments(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[TicketCommentResponse]:
    _, comments = await TicketService(db, current_user.organization_id).get_ticket_detail(
        ticket_id
    )
    return [TicketCommentResponse.model_validate(c) for c in comments]
