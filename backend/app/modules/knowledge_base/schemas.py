import uuid

from pydantic import BaseModel, Field


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CategoryResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class ArticleCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    category_id: uuid.UUID | None = None
    status: str = Field(default="draft", pattern="^(draft|published)$")


class ArticleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    category_id: uuid.UUID | None = None
    status: str | None = Field(default=None, pattern="^(draft|published)$")


class ArticleResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    category_id: uuid.UUID | None
    author_user_id: uuid.UUID
    title: str
    content: str
    status: str

    model_config = {"from_attributes": True}
