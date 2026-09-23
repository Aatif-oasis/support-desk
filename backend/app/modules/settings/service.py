import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_logs.service import AuditLogService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.settings.schemas import SettingsResponse, SettingsUpdateRequest


class SettingsService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.org_repo = OrganizationRepository(session)  # global — Organizations isn't tenant-scoped
        self.audit_service = AuditLogService(session, organization_id)

    async def get_settings(self) -> SettingsResponse:
        org = await self.org_repo.get_by_id(self.organization_id)
        return SettingsResponse(**org.settings)

    async def update_settings(
        self, actor_user_id: uuid.UUID, request: SettingsUpdateRequest
    ) -> SettingsResponse:
        org = await self.org_repo.get_by_id(self.organization_id)
        update_data = request.model_dump(exclude_unset=True, exclude_none=True)
        if "business_hours" in update_data:
            update_data["business_hours"] = {
                day: hours.model_dump() if hasattr(hours, "model_dump") else hours
                for day, hours in update_data["business_hours"].items()
            }
        merged = {**org.settings, **update_data}
        org.settings = merged
        await self.org_repo.update(org)
        await self.audit_service.log(
            actor_user_id, "settings.updated", "organization", self.organization_id, update_data
        )
        await self.session.commit()
        return SettingsResponse(**merged)
