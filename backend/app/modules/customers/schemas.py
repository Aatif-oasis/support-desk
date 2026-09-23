import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.shared.phone import normalize_phone


class IdentifyRequest(BaseModel):
    """
    Sent by the embeddable widget on page load and whenever it learns more
    about the visitor. external_id is generated and persisted by the widget
    itself (e.g. in localStorage) — it is NOT a login, just a stable handle
    so repeat visits/messages resolve to the same Customer row.
    """
    external_id: str = Field(min_length=1, max_length=255)
    email: str | None = None
    full_name: str | None = None
    phone: str | None = None
    browser: str | None = None
    operating_system: str | None = None
    country: str | None = None
    city: str | None = None
    language: str | None = None
    timezone: str | None = None
    current_page: str | None = Field(default=None, max_length=2048)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        # Optional here: the widget calls identify on page load, before the
        # visitor has told us anything. Only validate what was actually sent.
        return normalize_phone(value) if value else value


class IdentifyResponse(BaseModel):
    """
    Deliberately narrow — the widget only needs enough to know who it's
    talking to. Agent-internal fields (tags, notes, status) never go here.
    """
    id: uuid.UUID
    external_id: str
    full_name: str | None
    email: str | None

    model_config = {"from_attributes": True}


class CustomerUpdateRequest(BaseModel):
    """Agent-side profile edits — all optional, PATCH semantics."""
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None
    company: str | None = None
    tags: list[str] | None = None
    status: str | None = Field(default=None, pattern="^(active|blocked)$")

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else value


class NoteAddRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class CustomerResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    external_id: str
    email: str | None
    phone: str | None
    full_name: str | None
    company: str | None
    browser: str | None
    operating_system: str | None
    country: str | None
    city: str | None
    language: str | None
    timezone: str | None
    current_page: str | None
    tags: list[str]
    notes: list[dict]
    status: str
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}
