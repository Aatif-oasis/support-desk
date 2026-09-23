import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, Response, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.database import AsyncSessionLocal, get_db
from app.core.rate_limit import conversation_start_rate_limit, message_send_rate_limit
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.core.config import settings
from app.modules.conversations.captcha import (
    consume_pass,
    issue_challenge,
    verify_and_issue_pass,
)
from app.modules.conversations.schemas import (
    CaptchaChallengeResponse,
    CaptchaVerifyRequest,
    CaptchaVerifyResponse,
    AgentMessageCreateRequest,
    ConversationDetailResponse,
    ConversationNoteCreateRequest,
    ConversationNoteResponse,
    ConversationResponse,
    ConversationStartRequest,
    ConversationUpdateRequest,
    MessageResponse,
    PublicConversationHistoryResponse,
    PublicMessageCreateRequest,
    TagCreateRequest,
    TagResponse,
)
from app.modules.conversations.service import ConversationService
from app.modules.customers.service import CustomerService
from app.modules.users.repository import UserRepository
from app.websockets.connection_manager import connection_manager

public_router = APIRouter(prefix="/api/v1/public/{org_slug}/conversations", tags=["Public — Widget"])
router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


def conversation_response(conversation, customer=None) -> ConversationResponse:
    """
    Single place where a Conversation row plus its Customer row become the
    API shape. Every list/detail/update endpoint goes through here so the
    customer name and phone can never be present on one endpoint and
    missing on another — which is exactly how the dashboard ended up
    showing bare UUIDs before.
    """
    response = ConversationResponse.model_validate(conversation)
    if customer is not None:
        response.customer_name = customer.full_name
        response.customer_phone = customer.phone
        response.customer_email = customer.email
    return response


# ============================================================
# Public (widget-facing) — REST
# ============================================================

@public_router.post("", response_model=ConversationDetailResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(conversation_start_rate_limit)])
async def start_conversation(
    org_slug: str,
    request: ConversationStartRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ConversationDetailResponse:
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    service = ConversationService(db, organization_id)
    # Checked here rather than in the service because it guards this one
    # public doorway, not the act of starting a conversation — an agent or
    # a CRM opening one should never be asked to do arithmetic.
    if settings.CAPTCHA_ENABLED:
        await consume_pass(redis, request.captcha_pass)

    conversation, message = await service.start_conversation(
        redis, request.external_id, request.initial_message, request.full_name, request.phone
    )
    customer = await service.get_customer_for(conversation)
    return ConversationDetailResponse(
        **conversation_response(conversation, customer).model_dump(),
        messages=[MessageResponse.model_validate(message)],
    )


@public_router.get("/captcha", response_model=CaptchaChallengeResponse)
async def get_captcha(
    org_slug: str,
    redis: Redis = Depends(get_redis),
) -> CaptchaChallengeResponse:
    """A fresh question for the pre-chat form. The answer stays server-side."""
    return CaptchaChallengeResponse(**await issue_challenge(redis))


@public_router.post("/captcha/verify", response_model=CaptchaVerifyResponse)
async def verify_captcha(
    org_slug: str,
    request: CaptchaVerifyRequest,
    redis: Redis = Depends(get_redis),
) -> CaptchaVerifyResponse:
    """
    Called while the visitor is still on the form, so a wrong answer is
    reported next to the question rather than surfacing later as a failed
    message.
    """
    return CaptchaVerifyResponse(
        captcha_pass=await verify_and_issue_pass(redis, request.challenge_id, request.answer)
    )


@public_router.post("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read_by_customer(
    org_slug: str,
    conversation_id: uuid.UUID,
    external_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    """The visitor has the chat panel open, so the agent's replies are seen."""
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    await ConversationService(db, organization_id).mark_read_by_customer(
        redis, conversation_id, external_id
    )


@public_router.get("/{conversation_id}", response_model=PublicConversationHistoryResponse)
async def get_conversation_history(
    org_slug: str,
    conversation_id: uuid.UUID,
    external_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> PublicConversationHistoryResponse:
    """
    Lets the widget restore an in-progress chat after a page refresh.
    Without this the widget had no way to recover its thread, so every
    reload silently started a brand new conversation — one visitor showed
    up in the dashboard (and in any CRM listening to webhooks) as several
    unrelated chats.
    """
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    service = ConversationService(db, organization_id)
    conversation, messages = await service.get_public_conversation(conversation_id, external_id)
    return PublicConversationHistoryResponse(
        id=conversation.id,
        status=conversation.status,
        messages=[MessageResponse.model_validate(m) for m in messages],
        agent_last_read_at=conversation.agent_last_read_at,
    )


@public_router.post("/{conversation_id}/messages", response_model=MessageResponse, dependencies=[Depends(message_send_rate_limit)])
async def send_customer_message(
    org_slug: str,
    conversation_id: uuid.UUID,
    request: PublicMessageCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> MessageResponse:
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    service = ConversationService(db, organization_id)
    message = await service.add_customer_message(
        redis, conversation_id, request.external_id, request.content
    )
    return MessageResponse.model_validate(message)


# ============================================================
# Public (widget-facing) — WebSocket
# ============================================================

@public_router.websocket("/{conversation_id}/ws")
async def customer_conversation_socket(
    websocket: WebSocket,
    org_slug: str,
    conversation_id: uuid.UUID,
    external_id: str = Query(...),
) -> None:
    """
    Push-only from the server's perspective: the customer SENDS messages via
    the REST endpoint above (so a send has a normal request/response and can
    be retried on failure), and RECEIVES agent replies here in real time.
    Anything the client sends over this socket is treated as a keepalive/no-op.
    """
    async with AsyncSessionLocal() as db:
        try:
            organization_id = await CustomerService.resolve_organization_id(db, org_slug)
            service = ConversationService(db, organization_id)
            conversation, _ = await service.get_conversation_detail(conversation_id)
            customer = await service.customer_repo.get_by_external_id(organization_id, external_id)
            if not customer or customer.id != conversation.customer_id:
                await websocket.close(code=4403)
                return
        except Exception:
            await websocket.close(code=4404)
            return

    await websocket.accept()
    connection_manager.join_conversation(conversation_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.leave_conversation(conversation_id, websocket)


# ============================================================
# Agent-facing — REST
# ============================================================

@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[ConversationResponse]:
    service = ConversationService(db, current_user.organization_id)
    conversations = await service.list_conversations(
        status_filter, limit, offset, current_user.id, current_user.roles
    )
    customers = await service.customers_by_id(conversations)
    return [conversation_response(c, customers.get(c.customer_id)) for c in conversations]


@router.get("/search", response_model=list[ConversationResponse])
async def search_conversations(
    q: str = Query(min_length=1),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[ConversationResponse]:
    service = ConversationService(db, current_user.organization_id)
    results = await service.search_conversations(
        q, limit, offset, current_user.id, current_user.roles
    )
    customers = await service.customers_by_id(results)
    return [conversation_response(c, customers.get(c.customer_id)) for c in results]


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> ConversationDetailResponse:
    # Opening a conversation is an action, not just a read: if it's
    # unassigned, the agent opening it claims it (see
    # ConversationService.open_conversation_as_agent).
    service = ConversationService(db, current_user.organization_id)
    conversation, messages = await service.open_conversation_as_agent(
        redis, conversation_id, current_user.id, current_user.roles
    )
    customer = await service.get_customer_for(conversation)
    return ConversationDetailResponse(
        **conversation_response(conversation, customer).model_dump(),
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_agent_message(
    conversation_id: uuid.UUID,
    request: AgentMessageCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> MessageResponse:
    message = await ConversationService(db, current_user.organization_id).add_agent_message(
        redis, conversation_id, current_user.id, request.content, current_user.roles
    )
    return MessageResponse.model_validate(message)


@router.post("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read_by_agent(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> None:
    """The agent is looking at the chat, so the customer's messages are seen."""
    await ConversationService(db, current_user.organization_id).mark_read_by_agent(
        redis, conversation_id, current_user.id, current_user.roles
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    request: ConversationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> ConversationResponse:
    service = ConversationService(db, current_user.organization_id)
    conversation = await service.update_conversation(
        redis, conversation_id, current_user.id, current_user.roles, request
    )
    customer = await service.get_customer_for(conversation)
    return conversation_response(conversation, customer)


@router.post("/{conversation_id}/notes", response_model=ConversationNoteResponse, status_code=status.HTTP_201_CREATED)
async def add_conversation_note(
    conversation_id: uuid.UUID,
    request: ConversationNoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> ConversationNoteResponse:
    note = await ConversationService(db, current_user.organization_id).add_note(
        conversation_id, current_user.id, request.text, current_user.roles
    )
    return ConversationNoteResponse.model_validate(note)


@router.get("/{conversation_id}/notes", response_model=list[ConversationNoteResponse])
async def list_conversation_notes(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[ConversationNoteResponse]:
    notes = await ConversationService(db, current_user.organization_id).list_notes(
        conversation_id, current_user.id, current_user.roles
    )
    return [ConversationNoteResponse.model_validate(n) for n in notes]


@router.post("/{conversation_id}/tags", response_model=list[TagResponse])
async def assign_tag(
    conversation_id: uuid.UUID,
    request: TagCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[TagResponse]:
    tags = await ConversationService(db, current_user.organization_id).assign_tag(
        conversation_id, request.name
    )
    return [TagResponse.model_validate(t) for t in tags]


@router.get("/{conversation_id}/tags", response_model=list[TagResponse])
async def list_tags(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[TagResponse]:
    tags = await ConversationService(db, current_user.organization_id).list_conversation_tags(
        conversation_id
    )
    return [TagResponse.model_validate(t) for t in tags]


@router.delete("/{conversation_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(
    conversation_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> None:
    await ConversationService(db, current_user.organization_id).remove_tag(conversation_id, tag_id)


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: uuid.UUID,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> Response:
    data = await ConversationService(db, current_user.organization_id).export_conversation(
        conversation_id
    )
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["sender_type", "content", "created_at"])
        for m in data["messages"]:
            writer.writerow([m["sender_type"], m["content"], m["created_at"]])
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id}.csv"'},
        )
    import json as json_module

    return Response(
        content=json_module.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id}.json"'},
    )


# ============================================================
# Agent-facing — WebSocket (single persistent connection per agent session)
# ============================================================

@router.websocket("/ws/agent")
async def agent_socket(websocket: WebSocket, token: str = Query(...)) -> None:
    """
    Auth via query param rather than a header because browsers' native
    WebSocket API cannot set custom headers — this is the standard
    workaround, and it's why the JWT here is short-lived (same
    ACCESS_TOKEN_EXPIRE_MINUTES as everywhere else) rather than a separate
    long-lived socket token.

    On connect: joins the org-wide notification channel (dashboard badges/
    new-conversation alerts). The client can additionally send
    {"action": "watch", "conversation_id": "..."} to also receive full
    message content for a specific open chat, and
    {"action": "unwatch", "conversation_id": "..."} to stop.
    """
    try:
        payload = decode_access_token(token)
        organization_id = uuid.UUID(payload["organization_id"])
        user_id = uuid.UUID(payload["sub"])
        roles = list(payload.get("roles") or [])
    except (JWTError, KeyError, ValueError, TypeError):
        await websocket.close(code=4401)
        return

    # The REST endpoints re-check the account on every request, so a
    # suspended agent loses access immediately there. A socket is opened
    # once and then streams for as long as it stays open, so without this
    # check someone who left the company could keep reading live customer
    # messages until they closed the tab.
    async with AsyncSessionLocal() as session:
        account = await UserRepository(session).get_by_id(user_id)
        if not account or account.status == "suspended":
            await websocket.close(code=4401)
            return

    await websocket.accept()
    connection_manager.join_org_agents(organization_id, websocket)
    watched: set[uuid.UUID] = set()

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            raw_conversation_id = data.get("conversation_id")
            if action not in ("watch", "unwatch") or not raw_conversation_id:
                continue
            try:
                conversation_id = uuid.UUID(raw_conversation_id)
            except ValueError:
                continue

            if action == "watch":
                # Watching streams full message content, so it needs the
                # same ownership check as the REST endpoints. Otherwise an
                # agent blocked from opening a colleague's chat could still
                # subscribe to it over the socket and read every message.
                async with AsyncSessionLocal() as session:
                    service = ConversationService(session, organization_id)
                    try:
                        conversation = await service._get_conversation_or_404(conversation_id)
                        service.assert_can_access(conversation, user_id, roles)
                    except (NotFoundError, ForbiddenError):
                        continue

                connection_manager.join_conversation(conversation_id, websocket)
                watched.add(conversation_id)
            elif action == "unwatch":
                connection_manager.leave_conversation(conversation_id, websocket)
                watched.discard(conversation_id)
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.leave_org_agents(organization_id, websocket)
        for conversation_id in watched:
            connection_manager.leave_conversation(conversation_id, websocket)
