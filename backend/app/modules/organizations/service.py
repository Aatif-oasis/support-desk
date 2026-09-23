import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.audit_logs.service import AuditLogService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    OrganizationStatusUpdateRequest,
    OrganizationUpdateRequest,
)
from app.shared.pagination import Page


class OrganizationService:
    """
    Deliberately Super-Admin-only: individual organizations manage their own
    Departments/Teams/Users (Module 2's other sub-modules), but only the
    platform owner can list, edit, or suspend Organizations themselves.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        # organization_id=None: this repository is intentionally NOT
        # tenant-scoped, since Organizations IS the tenant boundary.
        self.repo = OrganizationRepository(session)

    async def list_organizations(self, limit: int, offset: int) -> Page:
        items = await self.repo.list(limit=limit, offset=offset)
        return Page(items=items, total=len(items), limit=limit, offset=offset)

    async def get_organization(self, organization_id: uuid.UUID):
        org = await self.repo.get_by_id(organization_id)
        if not org:
            raise NotFoundError("Organization not found.")
        return org

    async def update_organization(
        self, organization_id: uuid.UUID, request: OrganizationUpdateRequest
    ):
        org = await self.get_organization(organization_id)
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(org, field, value)
        await self.repo.update(org)
        await self.session.commit()
        return org

    async def update_status(
        self, actor_user_id: uuid.UUID, organization_id: uuid.UUID, request: OrganizationStatusUpdateRequest
    ):
        org = await self.get_organization(organization_id)
        org.subscription_status = request.subscription_status
        await self.repo.update(org)
        await AuditLogService(self.session, organization_id).log(
            actor_user_id, "organization.status_updated", "organization", organization_id,
            {"subscription_status": request.subscription_status},
        )
        await self.session.commit()
        return org
