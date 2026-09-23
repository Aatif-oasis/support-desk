import uuid

from sqlalchemy import select

from app.modules.customers.models import Customer
from app.shared.base_repository import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    async def get_by_external_id(
        self, organization_id: uuid.UUID, external_id: str
    ) -> Customer | None:
        query = select(Customer).where(
            Customer.organization_id == organization_id,
            Customer.external_id == external_id,
            Customer.deleted_at.is_(None),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
