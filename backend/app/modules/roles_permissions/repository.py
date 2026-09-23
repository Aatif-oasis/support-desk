import uuid

from sqlalchemy import insert, select

from app.modules.roles_permissions.models import Role, user_roles
from app.shared.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    model = Role

    async def get_system_role_by_name(self, name: str) -> Role | None:
        """System roles have organization_id IS NULL (see architecture doc)."""
        query = select(Role).where(
            Role.name == name, Role.organization_id.is_(None), Role.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def assign_role_to_user(self, user_id: uuid.UUID, role_id: uuid.UUID) -> None:
        await self.session.execute(insert(user_roles).values(user_id=user_id, role_id=role_id))
        await self.session.flush()

    async def get_role_names_for_user(self, user_id: uuid.UUID) -> list[str]:
        query = (
            select(Role.name)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(user_roles.c.user_id == user_id)
        )
        result = await self.session.execute(query)
        return [row[0] for row in result.all()]
