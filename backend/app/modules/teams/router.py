import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.teams.schemas import (
    TeamCreateRequest,
    TeamMemberRequest,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdateRequest,
)
from app.modules.teams.service import TeamService

router = APIRouter(prefix="/api/v1/teams", tags=["Teams"])


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[TeamResponse]:
    teams = await TeamService(db, current_user.organization_id).list_teams(limit, offset)
    return [TeamResponse.model_validate(t) for t in teams]


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    request: TeamCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> TeamResponse:
    team = await TeamService(db, current_user.organization_id).create_team(request)
    return TeamResponse.model_validate(team)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> TeamResponse:
    team = await TeamService(db, current_user.organization_id).get_team(team_id)
    return TeamResponse.model_validate(team)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    request: TeamUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> TeamResponse:
    team = await TeamService(db, current_user.organization_id).update_team(team_id, request)
    return TeamResponse.model_validate(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> None:
    await TeamService(db, current_user.organization_id).delete_team(team_id)


@router.post("/{team_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_team_member(
    team_id: uuid.UUID,
    request: TeamMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager")),
) -> None:
    await TeamService(db, current_user.organization_id).add_member(team_id, request.user_id)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager")),
) -> None:
    await TeamService(db, current_user.organization_id).remove_member(team_id, user_id)


@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_team_members(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[TeamMemberResponse]:
    members = await TeamService(db, current_user.organization_id).list_members(team_id)
    return [TeamMemberResponse.model_validate(m) for m in members]
