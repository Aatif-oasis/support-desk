import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterOrganizationRequest(BaseModel):
    """
    Self-serve org signup: creates the Organization AND its first user
    (who is granted the org_admin role) in one transaction.
    """
    organization_name: str = Field(min_length=2, max_length=255)
    admin_full_name: str = Field(min_length=2, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    email: EmailStr
    full_name: str
    status: str
    roles: list[str] = []

    model_config = {"from_attributes": True}


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    scopes: list[str] = Field(default_factory=list)


class ApiKeyCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    scopes: list[str]
    # Plaintext key is returned ONLY on creation — never again afterward.
    api_key: str


class ApiKeySummary(BaseModel):
    """
    What the Integrations screen lists. Deliberately has no api_key field
    — only the hash is stored server-side, so there is nothing to show
    even if this schema wanted to; the plaintext existed for one response
    only, at creation.
    """
    id: uuid.UUID
    name: str
    scopes: list[str]
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
