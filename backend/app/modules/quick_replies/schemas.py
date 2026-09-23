import uuid

from pydantic import BaseModel, Field


class QuickReplyCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10000)


class QuickReplyUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=10000)


class QuickReplyResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    content: str

    model_config = {"from_attributes": True}
