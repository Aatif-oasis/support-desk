import uuid

from pydantic import BaseModel, Field


class AutomationRuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    trigger_event: str = Field(pattern="^(conversation_created|message_received)$")
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    is_active: bool = True


class AutomationRuleUpdateRequest(BaseModel):
    name: str | None = None
    conditions: list[dict] | None = None
    actions: list[dict] | None = None
    is_active: bool | None = None


class AutomationRuleResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    trigger_event: str
    conditions: list[dict]
    actions: list[dict]
    is_active: bool

    model_config = {"from_attributes": True}
