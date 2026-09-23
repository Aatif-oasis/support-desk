import uuid

from pydantic import BaseModel, Field


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    department_id: uuid.UUID | None = None


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    department_id: uuid.UUID | None = None


class TeamResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID | None
    name: str

    model_config = {"from_attributes": True}


class TeamMemberRequest(BaseModel):
    user_id: uuid.UUID


class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str

    model_config = {"from_attributes": True}
