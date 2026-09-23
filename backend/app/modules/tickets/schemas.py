import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TicketCreateRequest(BaseModel):
    customer_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    assigned_agent_id: uuid.UUID | None = None
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")


class TicketUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|pending|resolved|closed)$")
    priority: str | None = Field(default=None, pattern="^(low|medium|high|urgent)$")
    assigned_agent_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None


class TicketCommentCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class TicketCommentResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_user_id: uuid.UUID
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    conversation_id: uuid.UUID | None
    department_id: uuid.UUID | None
    assigned_agent_id: uuid.UUID | None
    created_by_user_id: uuid.UUID
    subject: str
    description: str
    status: str
    priority: str
    resolved_at: datetime | None
    created_at: datetime

    # Same reasoning as ConversationResponse: an agent looking at a ticket
    # queue needs to see who it's for, and customer_id is a UUID that means
    # nothing to a person. Filled in by the router.
    customer_name: str | None = None
    customer_phone: str | None = None

    model_config = {"from_attributes": True}


class TicketDetailResponse(TicketResponse):
    comments: list[TicketCommentResponse]
