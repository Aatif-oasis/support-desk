import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    subscription_plan: str
    subscription_status: str
    settings: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationUpdateRequest(BaseModel):
    """All fields optional — PATCH semantics, only provided fields change."""
    name: str | None = Field(default=None, min_length=2, max_length=255)
    subscription_plan: str | None = None
    settings: dict | None = None


class OrganizationStatusUpdateRequest(BaseModel):
    subscription_status: str = Field(pattern="^(active|suspended|cancelled)$")
