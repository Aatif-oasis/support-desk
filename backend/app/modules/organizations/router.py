import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.auth.schemas import RegisterOrganizationRequest
from app.modules.auth.service import AuthService
from app.modules.organizations.schemas import (
    OrganizationResponse,
    OrganizationStatusUpdateRequest,
    OrganizationUpdateRequest,
)
from app.modules.organizations.service import OrganizationService
from app.shared.pagination import Page

router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["Organizations"],
    dependencies=[Depends(require_roles("super_admin"))],
)


@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    request: RegisterOrganizationRequest, db: AsyncSession = Depends(get_db)
) -> OrganizationResponse:
    """Onboards a new client and its first admin in one step, from Platform."""
    organization = await AuthService(db).create_organization_for_platform(request)
    return OrganizationResponse.model_validate(organization)


@router.get("", response_model=Page[OrganizationResponse])
async def list_organizations(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[OrganizationResponse]:
    result = await OrganizationService(db).list_organizations(limit, offset)
    return Page(
        items=[OrganizationResponse.model_validate(o) for o in result.items],
        total=result.total,
        limit=limit,
        offset=offset,
    )


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> OrganizationResponse:
    org = await OrganizationService(db).get_organization(organization_id)
    return OrganizationResponse.model_validate(org)


@router.patch("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: uuid.UUID,
    request: OrganizationUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    org = await OrganizationService(db).update_organization(organization_id, request)
    return OrganizationResponse.model_validate(org)


@router.patch("/{organization_id}/status", response_model=OrganizationResponse)
async def update_organization_status(
    organization_id: uuid.UUID,
    request: OrganizationStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("super_admin")),
) -> OrganizationResponse:
    """Suspend/reactivate/cancel an organization's subscription."""
    org = await OrganizationService(db).update_status(current_user.id, organization_id, request)
    return OrganizationResponse.model_validate(org)
