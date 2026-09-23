import uuid

from sqlalchemy import or_, select

from app.modules.knowledge_base.models import KnowledgeBaseArticle, KnowledgeBaseCategory
from app.shared.base_repository import BaseRepository


class KnowledgeBaseCategoryRepository(BaseRepository[KnowledgeBaseCategory]):
    model = KnowledgeBaseCategory


class KnowledgeBaseArticleRepository(BaseRepository[KnowledgeBaseArticle]):
    model = KnowledgeBaseArticle

    async def list_published(
        self, category_id: uuid.UUID | None, q: str | None, limit: int, offset: int
    ) -> list[KnowledgeBaseArticle]:
        query = self._base_query().where(KnowledgeBaseArticle.status == "published")
        if category_id:
            query = query.where(KnowledgeBaseArticle.category_id == category_id)
        if q:
            pattern = f"%{q}%"
            query = query.where(
                or_(
                    KnowledgeBaseArticle.title.ilike(pattern),
                    KnowledgeBaseArticle.content.ilike(pattern),
                )
            )
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_published_by_id(
        self, article_id: uuid.UUID
    ) -> KnowledgeBaseArticle | None:
        query = self._base_query().where(
            KnowledgeBaseArticle.id == article_id, KnowledgeBaseArticle.status == "published"
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all(
        self, status: str | None, limit: int, offset: int
    ) -> list[KnowledgeBaseArticle]:
        query = self._base_query()
        if status:
            query = query.where(KnowledgeBaseArticle.status == status)
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
