import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import CustomerUpdateRequest, IdentifyRequest
from app.modules.organizations.repository import OrganizationRepository
from app.modules.webhooks.service import WebhookService


class CustomerService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = CustomerRepository(session, organization_id=organization_id)
        self.webhook_service = WebhookService(session, organization_id)

    # ---------- Public (widget-facing) ----------

    @staticmethod
    async def resolve_organization_id(session: AsyncSession, org_slug: str) -> uuid.UUID:
        """
        organization_id=None here is intentional: resolving a slug happens
        before we know the tenant, same reasoning as UserRepository.get_by_email.
        """
        org_repo = OrganizationRepository(session)
        org = await org_repo.get_by_slug(org_slug)
        if not org:
            raise NotFoundError("Unknown organization.")
        return org.id

    async def identify(self, request: IdentifyRequest) -> Customer:
        """
        Upsert-by-external_id. Fields are only overwritten when the widget
        actually sends a value — this is progressive identification (an
        anonymous visitor becomes a named one over the conversation, we
        never want a later call with less info to blank out earlier data).
        """
        customer = await self.repo.get_by_external_id(self.organization_id, request.external_id)

        incoming = request.model_dump(exclude={"external_id"}, exclude_unset=True)
        incoming = {k: v for k, v in incoming.items() if v is not None}

        if customer is None:
            customer = Customer(
                organization_id=self.organization_id,
                external_id=request.external_id,
                **incoming,
            )
            customer.last_seen_at = datetime.now(timezone.utc)
            await self.repo.create(customer)
            await self.session.commit()
            await self.webhook_service.dispatch(
                "customer.created", {"customer_id": str(customer.id), "external_id": customer.external_id}
            )
        else:
            for field, value in incoming.items():
                setattr(customer, field, value)
            customer.last_seen_at = datetime.now(timezone.utc)
            await self.repo.update(customer)
            await self.session.commit()
            if incoming:
                await self.webhook_service.dispatch(
                    "customer.updated", {"customer_id": str(customer.id)}
                )

        return customer

    # ---------- Agent-facing ----------

    async def list_customers(self, limit: int, offset: int) -> list[Customer]:
        return await self.repo.list(limit=limit, offset=offset)

    async def get_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self.repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundError("Customer not found.")
        return customer

    async def update_customer(
        self, customer_id: uuid.UUID, request: CustomerUpdateRequest
    ) -> Customer:
        customer = await self.get_customer(customer_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(customer, field, value)
        await self.repo.update(customer)
        await self.session.commit()
        await self.webhook_service.dispatch("customer.updated", {"customer_id": str(customer.id)})
        return customer

    async def add_note(self, customer_id: uuid.UUID, text: str, author_user_id: uuid.UUID) -> Customer:
        customer = await self.get_customer(customer_id)
        customer.notes = [
            *customer.notes,
            {
                "text": text,
                "author_user_id": str(author_user_id),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        await self.repo.update(customer)
        await self.session.commit()
        return customer
