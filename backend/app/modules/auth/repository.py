from datetime import datetime, timezone

from sqlalchemy import select, update

from app.modules.auth.models import ApiKey, RefreshToken
from app.shared.base_repository import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_valid_by_hash(self, token_hash: str) -> RefreshToken | None:
        query = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def revoke_all_for_user(self, user_id) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )


class ApiKeyRepository(BaseRepository[ApiKey]):
    model = ApiKey

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        # Not tenant-scoped by design — the key IS what tells us the tenant.
        query = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.deleted_at.is_(None))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
