"""Shared pagination contract used by every module's list endpoints."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageParams(BaseModel):
    limit: int = 50
    offset: int = 0


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
