from sqlalchemy import select

from app.modules.users.models import User
from app.shared.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def list_agent_user_ids(self) -> list:
        """Active (non-suspended) users in this org — used to fan out org-wide notifications."""
        query = self._base_query().where(User.status != "suspended")
        result = await self.session.execute(query)
        return [u.id for u in result.scalars().all()]

    async def get_by_email(self, email: str) -> User | None:
        """
        Deliberately NOT organization-scoped — login happens before we know
        which tenant the user belongs to (email is globally unique across
        the platform), so this bypasses the tenant filter by querying
        directly rather than through _base_query().
        """
        query = select(User).where(User.email == email, User.deleted_at.is_(None))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
