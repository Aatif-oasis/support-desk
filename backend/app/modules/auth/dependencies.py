"""
These are the dependencies every OTHER module's routers will import to
authorize requests — e.g. `current_user: CurrentUser = Depends(get_current_user)`.
Centralizing this here means the JWT-decode-and-load-user logic exists
in exactly one place across all 19 modules.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token, hash_api_key
from app.modules.auth.repository import ApiKeyRepository
from app.modules.users.ip_guard import client_ip, enforce_ip_restriction
from app.modules.users.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


@dataclass
class CurrentUser:
    id: uuid.UUID
    organization_id: uuid.UUID | None
    roles: list[str]


async def get_current_user(
    http_request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(uuid.UUID(payload["sub"]))
    if not user or user.status == "suspended":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is no longer active.")

    # Checked on every request, not only at login. Otherwise an agent
    # could sign in at the office and carry the laptop home, and the token
    # would keep working for its full lifetime from anywhere.
    await enforce_ip_restriction(db, user, payload.get("roles", []), client_ip(http_request))

    return CurrentUser(
        id=user.id,
        organization_id=user.organization_id,
        roles=payload.get("roles", []),
    )


def require_roles(*allowed_roles: str):
    """Usage: Depends(require_roles('org_admin', 'super_admin'))"""
    async def checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not set(current_user.roles) & set(allowed_roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions.")
        return current_user
    return checker


@dataclass
class ApiKeyContext:
    """What an API-key-authenticated request knows about itself."""
    organization_id: uuid.UUID
    api_key_id: uuid.UUID
    name: str
    scopes: list[str]


async def get_api_key_context(
    x_api_key: str = Header(..., alias=settings.API_KEY_HEADER_NAME),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyContext:
    """
    For server-to-server (CRM integration) calls authenticated via API key
    instead of a user JWT — this is what makes the "any CRM can integrate"
    requirement possible without a human login.
    """
    api_key = await ApiKeyRepository(db).get_by_hash(hash_api_key(x_api_key))
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired API key.")

    # The previous check compared expires_at against created_at, which can
    # never be true — an expired key stayed valid forever. Compare against
    # now instead, normalizing naive timestamps (SQLite in the test suite
    # returns them without tzinfo) so the comparison can't raise.
    if api_key.expires_at is not None:
        expires_at = api_key.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired API key.")

    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return ApiKeyContext(
        organization_id=api_key.organization_id,
        api_key_id=api_key.id,
        name=api_key.name,
        scopes=list(api_key.scopes or []),
    )


async def get_organization_from_api_key(
    context: ApiKeyContext = Depends(get_api_key_context),
) -> uuid.UUID:
    """Kept for callers that only need the tenant id."""
    return context.organization_id
