import uuid

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.users.ip_guard import client_ip
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.auth.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeySummary,
    LoginRequest,
    RefreshRequest,
    RegisterOrganizationRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def verify_setup_key(x_setup_key: str | None = Header(default=None)) -> None:
    """
    Gate on creating an organization.

    Registration is the one endpoint that hands out a brand new tenant to
    a stranger, so on any deployment that is reachable from the internet
    it must not be open. Setting SIGNUP_SETUP_KEY turns it into an
    invitation: whoever holds the key can onboard a client, nobody else can.

    Left empty (the default for local development) the endpoint stays open,
    because forcing a key on a laptop only teaches people to paste secrets
    into shell history.
    """
    expected = settings.SIGNUP_SETUP_KEY
    if not expected:
        return

    # compare_digest so a wrong key can't be found one character at a time
    # by measuring how long the rejection takes.
    if not x_setup_key or not hmac.compare_digest(x_setup_key, expected):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Creating an organization needs a setup key. Ask whoever runs this server.",
        )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_setup_key)],
)
async def register_organization(
    request: RegisterOrganizationRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Creates a new Organization + its first Org Admin user, in one step."""
    return await AuthService(db).register_organization(request)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await AuthService(db).login(request, client_ip(http_request))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    return await AuthService(db).refresh(request.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    await AuthService(db).logout(request.refresh_token)


@router.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    request: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "super_admin")),
) -> ApiKeyCreateResponse:
    """Only Org Admins can mint API keys for their own organization."""
    return await AuthService(db).create_api_key(current_user.id, current_user.organization_id, request)


@router.get("/api-keys", response_model=list[ApiKeySummary])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "super_admin")),
) -> list[ApiKeySummary]:
    """The Integrations screen's list — names and scopes, never the secret."""
    keys = await AuthService(db).list_api_keys(current_user.organization_id)
    return [ApiKeySummary.model_validate(k) for k in keys]


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "super_admin")),
) -> None:
    """Revokes immediately — any integration using this key starts getting 401s."""
    await AuthService(db).revoke_api_key(current_user.id, current_user.organization_id, api_key_id)
