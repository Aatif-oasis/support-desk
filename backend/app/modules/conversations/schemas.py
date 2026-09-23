import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.shared.phone import normalize_phone


# ---------- Public (widget-facing) ----------

class CaptchaChallengeResponse(BaseModel):
    challenge_id: str
    question: str


class CaptchaVerifyRequest(BaseModel):
    challenge_id: str
    answer: str


class CaptchaVerifyResponse(BaseModel):
    captcha_pass: str


class ConversationStartRequest(BaseModel):
    # full_name/phone are required here (not just optional as in
    # IdentifyRequest) because starting a conversation is the one action
    # that's actually gated on "visitor details provided" — the widget's
    # pre-chat form enforces this client-side, but that's bypassable by
    # anyone calling this endpoint directly, so it's enforced again here.
    external_id: str = Field(min_length=1, max_length=255)
    initial_message: str = Field(min_length=1, max_length=10000)
    full_name: str = Field(min_length=2, max_length=255)
    phone: str = Field(min_length=1, max_length=50)

    # Only used when CAPTCHA_ENABLED is on; absent otherwise so older
    # embeds of the widget keep working. The pass is handed out by
    # /captcha/verify once the visitor answers correctly at the form.
    captcha_pass: str | None = None

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        # The widget checks this too, but that check protects the person
        # typing, not the data: anyone can POST here directly.
        return normalize_phone(value)


class PublicMessageCreateRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10000)


# ---------- Shared response shapes ----------

class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: str
    sender_id: uuid.UUID | None
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    assigned_agent_id: uuid.UUID | None
    department_id: uuid.UUID | None
    channel: str
    status: str
    started_at: datetime
    closed_at: datetime | None
    last_message_at: datetime | None
    # Read receipts: when each side last had the chat open. A message is
    # "seen" if the other side's timestamp is later than it.
    customer_last_read_at: datetime | None = None
    agent_last_read_at: datetime | None = None

    # Denormalized customer identity. The widget's pre-chat form collects
    # name + phone, but until now an agent (or a CRM reading this API) only
    # ever saw customer_id — a UUID that means nothing to a human. These are
    # filled in by the router from the Customer row; they default to None so
    # model_validate(conversation) still works anywhere that doesn't have
    # the customer loaded.
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class PublicConversationHistoryResponse(BaseModel):
    """
    What the widget gets back when it reconnects to a conversation it
    already started (page refresh, revisit). Deliberately narrower than
    ConversationDetailResponse — a customer's browser has no business
    seeing assigned_agent_id, department_id or org internals.
    """
    id: uuid.UUID
    status: str
    messages: list[MessageResponse]
    # Only the agent's timestamp is sent to the widget: the visitor needs
    # to know whether an agent has read their message, and nothing more.
    agent_last_read_at: datetime | None = None


# ---------- Agent-facing ----------

class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TagResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class ConversationNoteCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ConversationNoteResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    author_user_id: uuid.UUID
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class ConversationUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|pending|closed)$")
    assigned_agent_id: uuid.UUID | None = None
