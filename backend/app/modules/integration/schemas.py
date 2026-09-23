import uuid

from pydantic import BaseModel, Field


class IntegrationPingResponse(BaseModel):
    """First call any CRM makes — proves the key works before wiring anything else."""
    organization_id: uuid.UUID
    api_key_name: str
    scopes: list[str]


class IntegrationReplyRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    # Optional: if the CRM knows which Chat Support user its operator maps to,
    # pass the id and the reply is attributed to that agent. Left out, the
    # message is stored as an agent reply with no specific author, which is
    # the right shape for a bot or a shared CRM inbox.
    agent_user_id: uuid.UUID | None = None


class IntegrationConversationUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|pending|closed)$")
    assigned_agent_id: uuid.UUID | None = None


class IntegrationCustomerResponse(BaseModel):
    id: uuid.UUID
    external_id: str
    full_name: str | None
    phone: str | None
    email: str | None
    company: str | None
    country: str | None
    city: str | None
    language: str | None
    timezone: str | None
    current_page: str | None
    status: str

    model_config = {"from_attributes": True}
