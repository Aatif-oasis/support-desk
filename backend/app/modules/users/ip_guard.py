"""
Working out where a request actually came from, and enforcing the office
lock.

The subtle part is the address itself. Behind nginx every request appears
to come from the proxy, so the real client sits in X-Forwarded-For — but
that header is set by the client on a direct connection, meaning anyone
could add it and claim to be in the office. Trusting it is correct behind
a proxy and a security hole without one, which is why it is a setting
rather than a guess.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.users.models import User

# An admin can always get in. They are the only person who can lift a
# lock, so locking them out would leave nobody able to undo it.
EXEMPT_ROLES = {"org_admin", "super_admin"}


def client_ip(request: Request) -> str | None:
    """The caller's address, as far as this deployment can be sure of it."""
    if settings.TRUST_FORWARDED_FOR:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First entry is the original client; the rest are proxies.
            return forwarded.split(",")[0].strip()

    return request.client.host if request.client else None


def is_ip_allowed(user: User, address: str | None) -> bool:
    """No address on the account means no restriction."""
    if not user.allowed_ip:
        return True
    return address == user.allowed_ip


async def enforce_ip_restriction(
    session: AsyncSession, user: User, roles: list[str], address: str | None
) -> None:
    """
    Raises 403 when an agent is signing in from somewhere they shouldn't
    be, and records the attempt so an admin can see it later.

    Recording matters as much as blocking: without it the only signal is
    an agent saying "it won't let me in", with no way to tell a genuine
    office move from someone trying from home.
    """
    if EXEMPT_ROLES & set(roles or []):
        return
    if is_ip_allowed(user, address):
        return

    user.last_blocked_ip = address
    user.last_blocked_at = datetime.now(timezone.utc)
    await session.commit()

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "This account can only be used from its approved location. "
        "Ask your administrator if you have moved.",
    )
