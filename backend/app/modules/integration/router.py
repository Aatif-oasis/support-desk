"""
The API-key surface for external systems (CRM / ERP / bots).

Everything here authenticates with the X-API-Key header instead of a user
JWT, so a CRM can run unattended with no human login and no expiring token
to refresh. Webhooks already pushed events outward; this is the other
direction — the CRM can read a conversation and, crucially, write a reply
back into it, which is what makes the integration two-way.

The key identifies the tenant, so every service below is constructed with
that organization_id and inherits the same tenant isolation the rest of
the app uses. There is no path here that can reach another org's data.
"""
import uuid

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.auth.dependencies import ApiKeyContext, get_api_key_context
from app.modules.conversations.router import conversation_response
from app.modules.conversations.schemas import (
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageResponse,
)
from app.modules.conversations.service import ConversationService
from app.modules.customers.repository import CustomerRepository
from app.modules.integration.schemas import (
    IntegrationConversationUpdateRequest,
    IntegrationCustomerResponse,
    IntegrationPingResponse,
    IntegrationReplyRequest,
)
from app.modules.webhooks.schemas import (
    WebhookSubscriptionCreateRequest,
    WebhookSubscriptionCreateResponse,
    WebhookSubscriptionResponse,
)
from app.modules.webhooks.service import WebhookService

router = APIRouter(prefix="/api/v1/integration", tags=["Integration — API Key"])


@router.get("/ping", response_model=IntegrationPingResponse)
async def ping(context: ApiKeyContext = Depends(get_api_key_context)) -> IntegrationPingResponse:
    return IntegrationPingResponse(
        organization_id=context.organization_id,
        api_key_name=context.name,
        scopes=context.scopes,
    )


# ---------- Conversations ----------

@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> list[ConversationResponse]:
    service = ConversationService(db, context.organization_id)
    conversations = await service.list_conversations(status_filter, limit, offset)
    customers = await service.customers_by_id(conversations)
    return [conversation_response(c, customers.get(c.customer_id)) for c in conversations]


@router.get("/conversations/search", response_model=list[ConversationResponse])
async def search_conversations(
    q: str = Query(min_length=1),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> list[ConversationResponse]:
    service = ConversationService(db, context.organization_id)
    results = await service.search_conversations(q, limit, offset)
    customers = await service.customers_by_id(results)
    return [conversation_response(c, customers.get(c.customer_id)) for c in results]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> ConversationDetailResponse:
    """
    Unlike the agent endpoint, reading here never claims the conversation —
    a CRM polling for context must not silently assign chats to itself and
    hide them from the humans waiting to pick them up.
    """
    service = ConversationService(db, context.organization_id)
    conversation, messages = await service.get_conversation_detail(conversation_id)
    customer = await service.get_customer_for(conversation)
    return ConversationDetailResponse(
        **conversation_response(conversation, customer).model_dump(),
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reply_to_conversation(
    conversation_id: uuid.UUID,
    request: IntegrationReplyRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> MessageResponse:
    """
    The CRM writes back into the chat. The reply goes down the same
    WebSocket path as a dashboard reply, so the visitor sees it appear
    immediately, and it fires the same message.sent webhook.
    """
    message = await ConversationService(db, context.organization_id).add_integration_message(
        redis, conversation_id, request.content, request.agent_user_id
    )
    return MessageResponse.model_validate(message)


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    request: IntegrationConversationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> ConversationResponse:
    """Close a chat, or route it to a specific agent, from the CRM side."""
    service = ConversationService(db, context.organization_id)
    conversation = await service.update_conversation(
        redis,
        conversation_id,
        # An API key is not a user, so there is no "own conversations only"
        # restriction to apply — it acts with org-admin scope within its
        # own tenant, which is what the key already grants.
        current_user_id=None,
        current_user_roles=["org_admin"],
        request=ConversationUpdateRequest(**request.model_dump(exclude_unset=True)),
    )
    customer = await service.get_customer_for(conversation)
    return conversation_response(conversation, customer)


# ---------- Customers ----------

@router.get("/customers", response_model=list[IntegrationCustomerResponse])
async def list_customers(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> list[IntegrationCustomerResponse]:
    customers = await CustomerRepository(db, organization_id=context.organization_id).list(
        limit=limit, offset=offset
    )
    return [IntegrationCustomerResponse.model_validate(c) for c in customers]


@router.get("/customers/{customer_id}", response_model=IntegrationCustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> IntegrationCustomerResponse:
    from app.core.exceptions import NotFoundError

    customer = await CustomerRepository(db, organization_id=context.organization_id).get_by_id(
        customer_id
    )
    if not customer:
        raise NotFoundError("Customer not found.")
    return IntegrationCustomerResponse.model_validate(customer)


# ---------- Webhooks (so the CRM can register its own receiver) ----------

@router.get("/webhooks", response_model=list[WebhookSubscriptionResponse])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> list[WebhookSubscriptionResponse]:
    subs = await WebhookService(db, context.organization_id).list_subscriptions()
    return [WebhookSubscriptionResponse.model_validate(s) for s in subs]


@router.post(
    "/webhooks",
    response_model=WebhookSubscriptionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    request: WebhookSubscriptionCreateRequest,
    db: AsyncSession = Depends(get_db),
    context: ApiKeyContext = Depends(get_api_key_context),
) -> WebhookSubscriptionCreateResponse:
    subscription = await WebhookService(db, context.organization_id).create_subscription(request)
    return WebhookSubscriptionCreateResponse(
        **WebhookSubscriptionResponse.model_validate(subscription).model_dump(),
        secret=subscription.secret,
    )
