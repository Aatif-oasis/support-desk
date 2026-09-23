import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

VALID_EVENTS = {
    "chat.created",
    "chat.closed",
    "message.received",
    "message.sent",
    "customer.created",
    "customer.updated",
    "ticket.created",
    "ticket.updated",
}


class WebhookSubscriptionCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    events: list[str] = Field(min_length=1)

    @field_validator("events")
    @classmethod
    def validate_events(cls, value: list[str]) -> list[str]:
        unknown = set(value) - VALID_EVENTS
        if unknown:
            raise ValueError(f"Unknown event(s): {sorted(unknown)}. Valid: {sorted(VALID_EVENTS)}")
        return value


class WebhookSubscriptionUpdateRequest(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookSubscriptionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool

    model_config = {"from_attributes": True}


class WebhookSubscriptionCreateResponse(WebhookSubscriptionResponse):
    # Plaintext secret is returned ONLY on creation — same pattern as API keys.
    secret: str


class WebhookDeliveryResponse(BaseModel):
    id: uuid.UUID
    subscription_id: uuid.UUID
    event: str
    response_status: int | None
    error: str | None
    delivered_at: datetime

    model_config = {"from_attributes": True}
