import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.teams.models import Team
from app.modules.teams.repository import TeamRepository
from app.modules.teams.schemas import TeamCreateRequest, TeamUpdateRequest
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class TeamService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = TeamRepository(session, organization_id=organization_id)
        self.user_repo = UserRepository(session, organization_id=organization_id)

    async def list_teams(self, limit: int, offset: int) -> list[Team]:
        return await self.repo.list(limit=limit, offset=offset)

    async def get_team(self, team_id: uuid.UUID) -> Team:
        team = await self.repo.get_by_id(team_id)
        if not team:
            raise NotFoundError("Team not found.")
        return team

    async def create_team(self, request: TeamCreateRequest) -> Team:
        team = await self.repo.create(
            Team(
                organization_id=self.organization_id,
                department_id=request.department_id,
                name=request.name,
            )
        )
        await self.session.commit()
        return team

    async def update_team(self, team_id: uuid.UUID, request: TeamUpdateRequest) -> Team:
        team = await self.get_team(team_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(team, field, value)
        await self.repo.update(team)
        await self.session.commit()
        return team

    async def delete_team(self, team_id: uuid.UUID) -> None:
        team = await self.get_team(team_id)
        await self.repo.soft_delete(team)
        await self.session.commit()

    async def add_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.get_team(team_id)  # 404 if team doesn't exist / wrong org
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found in this organization.")
        await self.repo.add_member(team_id, user_id)
        await self.session.commit()

    async def remove_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.get_team(team_id)
        await self.repo.remove_member(team_id, user_id)
        await self.session.commit()

    async def list_members(self, team_id: uuid.UUID) -> list[User]:
        await self.get_team(team_id)
        return await self.repo.list_members(team_id)
