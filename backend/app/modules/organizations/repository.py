from sqlalchemy import select

from app.modules.organizations.models import Organization
from app.shared.base_repository import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    async def get_by_slug(self, slug: str) -> Organization | None:
        query = select(Organization).where(
            Organization.slug == slug, Organization.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
