"""
BaseRepository is the ONLY place raw SQLAlchemy queries should live for
tenant-scoped tables. It exists so no individual module repository can
forget the organization_id filter and accidentally leak cross-tenant data
— every read/update/delete goes through here and the tenant filter is
applied unconditionally, not left to each repository author to remember.

Module repositories subclass this and add entity-specific query methods
(e.g. UserRepository.get_by_email) — they should not reimplement get/list/
create/update/delete for the common case.
"""
import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID | None = None):
        """
        `organization_id=None` is only valid for platform-global repositories
        (e.g. permissions, or Super Admin's own Organizations repository).
        Every tenant-scoped module repository MUST receive a real
        organization_id from the authenticated request context.
        """
        self.session = session
        self.organization_id = organization_id

    def _base_query(self):
        query = select(self.model).where(self.model.deleted_at.is_(None))
        if self.organization_id is not None and hasattr(self.model, "organization_id"):
            query = query.where(self.model.organization_id == self.organization_id)
        return query

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelType | None:
        query = self._base_query().where(self.model.id == entity_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(self, limit: int = 50, offset: int = 0) -> list[ModelType]:
        query = self._base_query().limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, entity: ModelType) -> ModelType:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: ModelType) -> ModelType:
        await self.session.flush()
        return entity

    async def soft_delete(self, entity: ModelType) -> None:
        from datetime import datetime, timezone
        entity.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
