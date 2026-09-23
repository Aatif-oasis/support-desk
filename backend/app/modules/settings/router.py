from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.settings.schemas import SettingsResponse, SettingsUpdateRequest
from app.modules.settings.service import SettingsService

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> SettingsResponse:
    return await SettingsService(db, current_user.organization_id).get_settings()


@router.patch("", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> SettingsResponse:
    return await SettingsService(db, current_user.organization_id).update_settings(
        current_user.id, request
    )
