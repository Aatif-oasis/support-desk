import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.knowledge_base.models import KnowledgeBaseArticle, KnowledgeBaseCategory
from app.modules.knowledge_base.repository import (
    KnowledgeBaseArticleRepository,
    KnowledgeBaseCategoryRepository,
)
from app.modules.knowledge_base.schemas import (
    ArticleCreateRequest,
    ArticleUpdateRequest,
    CategoryCreateRequest,
)


class KnowledgeBaseService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.category_repo = KnowledgeBaseCategoryRepository(session, organization_id=organization_id)
        self.article_repo = KnowledgeBaseArticleRepository(session, organization_id=organization_id)

    # ---------- Categories ----------

    async def list_categories(self) -> list[KnowledgeBaseCategory]:
        return await self.category_repo.list(limit=200, offset=0)

    async def create_category(self, request: CategoryCreateRequest) -> KnowledgeBaseCategory:
        category = await self.category_repo.create(
            KnowledgeBaseCategory(organization_id=self.organization_id, name=request.name)
        )
        await self.session.commit()
        return category

    # ---------- Articles (agent-facing) ----------

    async def list_articles(self, status: str | None, limit: int, offset: int):
        return await self.article_repo.list_all(status, limit, offset)

    async def create_article(
        self, author_user_id: uuid.UUID, request: ArticleCreateRequest
    ) -> KnowledgeBaseArticle:
        article = await self.article_repo.create(
            KnowledgeBaseArticle(
                organization_id=self.organization_id,
                category_id=request.category_id,
                author_user_id=author_user_id,
                title=request.title,
                content=request.content,
                status=request.status,
            )
        )
        await self.session.commit()
        return article

    async def get_article(self, article_id: uuid.UUID) -> KnowledgeBaseArticle:
        article = await self.article_repo.get_by_id(article_id)
        if not article:
            raise NotFoundError("Article not found.")
        return article

    async def update_article(
        self, article_id: uuid.UUID, request: ArticleUpdateRequest
    ) -> KnowledgeBaseArticle:
        article = await self.get_article(article_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(article, field, value)
        await self.article_repo.update(article)
        await self.session.commit()
        return article

    async def delete_article(self, article_id: uuid.UUID) -> None:
        article = await self.get_article(article_id)
        await self.article_repo.soft_delete(article)
        await self.session.commit()

    # ---------- Public (widget-facing) ----------

    async def list_published(
        self, category_id: uuid.UUID | None, q: str | None, limit: int, offset: int
    ) -> list[KnowledgeBaseArticle]:
        return await self.article_repo.list_published(category_id, q, limit, offset)

    async def get_published_article(self, article_id: uuid.UUID) -> KnowledgeBaseArticle:
        article = await self.article_repo.get_published_by_id(article_id)
        if not article:
            raise NotFoundError("Article not found.")
        return article
