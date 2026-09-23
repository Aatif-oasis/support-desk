"""
Security primitives shared across the app.
This is the ONLY place password hashing, JWT encode/decode, and API key
hashing should happen — services call into here, they never touch
passlib/jose directly. Keeping it centralized means a future crypto change
(e.g. rotating JWT_SECRET_KEY, switching hash schemes) touches one file.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------- Passwords ----------

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


# ---------- JWT Access Tokens ----------

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    `subject` is the user_id (as a string). `extra_claims` typically carries
    organization_id and role codes so the API layer can authorize requests
    without a DB round-trip on every call.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jose.JWTError if invalid/expired — caller maps to HTTP 401."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ---------- Refresh Tokens ----------
# Refresh tokens are opaque random strings, not JWTs. Only their HASH is
# stored in the DB (refresh_tokens.token_hash) so a DB leak doesn't expose
# usable tokens — mirrors how API keys are stored.

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- API Keys ----------
# Format: oc_live_<32 random chars>. Prefix makes leaked-key scanning
# (e.g. in git history, logs) straightforward for the org's security team.

def generate_api_key() -> str:
    return f"oc_live_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()
