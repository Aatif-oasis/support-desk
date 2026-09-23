"""
A door into "my organization" for the workspace's own admin.

The main organizations router is locked to super_admin — a platform
owner managing every tenant. An org_admin needs exactly one fact from
that table for themselves: their own slug, to build the widget's embed
snippet. This tiny router exists so that one fact doesn't require
opening up the whole platform-management surface to every admin.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, get_current_user
from app.modules.organizations.schemas import OrganizationResponse
from app.modules.organizations.service import OrganizationService

router = APIRouter(prefix="/api/v1/my-organization", tags=["My Organization"])


@router.get("", response_model=OrganizationResponse)
async def get_my_organization(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> OrganizationResponse:
    """
    Any signed-in member of a tenant can read their own organization's
    public-ish details (name, slug) — there's nothing here an agent
    couldn't already infer from the widget URL they're chatting through.
    A super_admin has no organization_id and gets a 404, same as anyone
    whose organization was deleted from under them.
    """
    org = await OrganizationService(db).get_organization(current_user.organization_id)
    return OrganizationResponse.model_validate(org)
