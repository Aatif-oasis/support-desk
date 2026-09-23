import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.users.ip_guard import client_ip
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    UserInviteRequest,
    IpRestrictionRequest,
    MyIpResponse,
    PasswordResetRequest,
    UserResponse,
    UserRoleAssignRequest,
    UserUpdateRequest,
)
from app.modules.users.service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


def _to_response(user, roles: list[str]) -> UserResponse:
    return UserResponse(
        id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        status=user.status,
        roles=roles,
        allowed_ip=user.allowed_ip,
        last_blocked_ip=user.last_blocked_ip,
        last_blocked_at=user.last_blocked_at,
    )


@router.get("", response_model=list[UserResponse])
async def list_users(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager")),
) -> list[UserResponse]:
    pairs = await UserService(db, current_user.organization_id).list_users(limit, offset)
    return [_to_response(u, roles) for u, roles in pairs]


class AgentSummaryResponse(BaseModel):
    """
    Deliberately thinner than UserResponse: no roles, no email-based admin
    surface — just enough for any agent to turn an assigned_agent_id into a
    human name in the UI.
    """
    id: uuid.UUID
    full_name: str
    status: str

    model_config = {"from_attributes": True}


@router.get("/my-ip", response_model=MyIpResponse)
async def my_ip(
    http_request: Request,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> MyIpResponse:
    """
    Shows the admin the address this server sees them on, so they can copy
    it instead of guessing. Guessing usually means typing the address the
    router shows inside the office (192.168.x.x), which never reaches the
    server and would lock the agent out completely.
    """
    return MyIpResponse(
        address=client_ip(http_request),
        trusting_proxy_header=settings.TRUST_FORWARDED_FOR,
    )


# Declared before /{user_id} so the literal path wins the route match.
@router.get("/agents", response_model=list[AgentSummaryResponse])
async def list_agent_names(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[AgentSummaryResponse]:
    """
    /api/v1/users is admin-only, which meant an agent-role dashboard could
    not resolve "who is this conversation assigned to" at all — the call
    failed with 403 and took the whole conversation list down with it.
    This endpoint exposes only names, so agents can have it.
    """
    users = await UserRepository(db, organization_id=current_user.organization_id).list(
        limit=200, offset=0
    )
    return [AgentSummaryResponse.model_validate(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    request: UserInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> UserResponse:
    user, roles = await UserService(db, current_user.organization_id).invite_user(current_user.id, request)
    return _to_response(user, roles)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager")),
) -> UserResponse:
    user, roles = await UserService(db, current_user.organization_id).get_user(user_id)
    return _to_response(user, roles)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    request: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> UserResponse:
    user, roles = await UserService(db, current_user.organization_id).update_user(user_id, request)
    return _to_response(user, roles)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> None:
    """Soft deactivate — sets status to 'suspended' rather than deleting the row."""
    await UserService(db, current_user.organization_id).deactivate_user(current_user.id, user_id)


@router.post("/{user_id}/ip-restriction", response_model=UserResponse)
async def set_ip_restriction(
    user_id: uuid.UUID,
    request: IpRestrictionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> UserResponse:
    """Admin-only: pin a user to one address, or send null to unpin them."""
    service = UserService(db, current_user.organization_id)
    await service.set_allowed_ip(current_user.id, user_id, request.allowed_ip)
    user, roles = await service.get_user(user_id)
    return UserResponse(**user.__dict__, roles=roles)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
async def reset_password(
    user_id: uuid.UUID,
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> UserResponse:
    """
    Admin-only: sets a new password for a locked-out user. Deliberately
    not available to team managers — being able to set someone's password
    is being able to sign in as them.
    """
    service = UserService(db, current_user.organization_id)
    await service.reset_password(current_user.id, user_id, request.new_password)
    user, roles = await service.get_user(user_id)
    return UserResponse(**user.__dict__, roles=roles)


@router.post("/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> UserResponse:
    """Undo a suspension — for someone returning, or suspended by mistake."""
    service = UserService(db, current_user.organization_id)
    await service.reactivate_user(current_user.id, user_id)
    user, roles = await service.get_user(user_id)
    return UserResponse(**user.__dict__, roles=roles)


@router.post("/{user_id}/roles", response_model=UserResponse)
async def assign_role(
    user_id: uuid.UUID,
    request: UserRoleAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> UserResponse:
    service = UserService(db, current_user.organization_id)
    roles = await service.assign_role(current_user.id, user_id, request.role)
    user, _ = await service.get_user(user_id)
    return _to_response(user, roles)
