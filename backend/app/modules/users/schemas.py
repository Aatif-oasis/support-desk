from datetime import datetime
import uuid

from pydantic import BaseModel, EmailStr, Field


class UserInviteRequest(BaseModel):
    """
    Creates a user directly with a temporary password rather than a true
    email-invite flow — email delivery is out of scope for Module 2
    (belongs with the Notifications module later in the roadmap).
    """
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    temporary_password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(org_admin|team_manager|agent)$")


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    status: str | None = Field(default=None, pattern="^(active|invited|suspended)$")


class IpRestrictionRequest(BaseModel):
    """Null clears the lock — that is how an admin lets someone work from home."""
    allowed_ip: str | None = Field(default=None, max_length=45)


class MyIpResponse(BaseModel):
    """What the server sees this request coming from."""
    address: str | None
    trusting_proxy_header: bool


class PasswordResetRequest(BaseModel):
    """An admin setting a new password for someone who is locked out."""
    new_password: str = Field(min_length=8, max_length=128)


class UserRoleAssignRequest(BaseModel):
    role: str = Field(pattern="^(org_admin|team_manager|agent)$")


class UserResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    email: EmailStr
    full_name: str
    status: str
    roles: list[str] = []
    allowed_ip: str | None = None
    last_blocked_ip: str | None = None
    last_blocked_at: datetime | None = None

    model_config = {"from_attributes": True}
