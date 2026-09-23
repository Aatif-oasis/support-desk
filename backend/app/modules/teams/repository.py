import uuid

from sqlalchemy import delete, insert, select

from app.modules.teams.models import Team, user_teams
from app.modules.users.models import User
from app.shared.base_repository import BaseRepository


class TeamRepository(BaseRepository[Team]):
    model = Team

    async def add_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        # Ignore if already a member — idempotent add.
        existing = await self.session.execute(
            select(user_teams).where(
                user_teams.c.team_id == team_id, user_teams.c.user_id == user_id
            )
        )
        if existing.first() is None:
            await self.session.execute(insert(user_teams).values(team_id=team_id, user_id=user_id))
            await self.session.flush()

    async def remove_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(user_teams).where(
                user_teams.c.team_id == team_id, user_teams.c.user_id == user_id
            )
        )
        await self.session.flush()

    async def list_members(self, team_id: uuid.UUID) -> list[User]:
        query = (
            select(User)
            .join(user_teams, user_teams.c.user_id == User.id)
            .where(user_teams.c.team_id == team_id, User.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
