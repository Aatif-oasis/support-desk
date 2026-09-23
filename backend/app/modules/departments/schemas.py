import uuid

from pydantic import BaseModel, Field


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)


class DepartmentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}
