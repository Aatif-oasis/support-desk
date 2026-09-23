import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import kb_public_rate_limit
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.customers.service import CustomerService
from app.modules.knowledge_base.schemas import (
    ArticleCreateRequest,
    ArticleResponse,
    ArticleUpdateRequest,
    CategoryCreateRequest,
    CategoryResponse,
)
from app.modules.knowledge_base.service import KnowledgeBaseService

public_router = APIRouter(prefix="/api/v1/public/{org_slug}/knowledge-base", tags=["Public — Widget"])
router = APIRouter(prefix="/api/v1/knowledge-base", tags=["Knowledge Base"])


# ---------- Public (widget-facing, no auth — published only) ----------

@public_router.get("/articles", response_model=list[ArticleResponse], dependencies=[Depends(kb_public_rate_limit)])
async def public_list_articles(
    org_slug: str,
    category_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ArticleResponse]:
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    articles = await KnowledgeBaseService(db, organization_id).list_published(
        category_id, q, limit, offset
    )
    return [ArticleResponse.model_validate(a) for a in articles]


@public_router.get("/articles/{article_id}", response_model=ArticleResponse, dependencies=[Depends(kb_public_rate_limit)])
async def public_get_article(
    org_slug: str, article_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ArticleResponse:
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    article = await KnowledgeBaseService(db, organization_id).get_published_article(article_id)
    return ArticleResponse.model_validate(article)


# ---------- Agent-facing ----------

@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[CategoryResponse]:
    categories = await KnowledgeBaseService(db, current_user.organization_id).list_categories()
    return [CategoryResponse.model_validate(c) for c in categories]


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    request: CategoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> CategoryResponse:
    category = await KnowledgeBaseService(db, current_user.organization_id).create_category(request)
    return CategoryResponse.model_validate(category)


@router.get("/articles", response_model=list[ArticleResponse])
async def list_articles(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[ArticleResponse]:
    articles = await KnowledgeBaseService(db, current_user.organization_id).list_articles(
        status_filter, limit, offset
    )
    return [ArticleResponse.model_validate(a) for a in articles]


@router.post("/articles", response_model=ArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_article(
    request: ArticleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager")),
) -> ArticleResponse:
    article = await KnowledgeBaseService(db, current_user.organization_id).create_article(
        current_user.id, request
    )
    return ArticleResponse.model_validate(article)


@router.get("/articles/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> ArticleResponse:
    article = await KnowledgeBaseService(db, current_user.organization_id).get_article(article_id)
    return ArticleResponse.model_validate(article)


@router.patch("/articles/{article_id}", response_model=ArticleResponse)
async def update_article(
    article_id: uuid.UUID,
    request: ArticleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager")),
) -> ArticleResponse:
    article = await KnowledgeBaseService(db, current_user.organization_id).update_article(
        article_id, request
    )
    return ArticleResponse.model_validate(article)


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager")),
) -> None:
    await KnowledgeBaseService(db, current_user.organization_id).delete_article(article_id)
