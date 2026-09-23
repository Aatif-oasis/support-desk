import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.departments.models import Department
from app.modules.departments.repository import DepartmentRepository
from app.modules.departments.schemas import DepartmentCreateRequest, DepartmentUpdateRequest


class DepartmentService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.repo = DepartmentRepository(session, organization_id=organization_id)
        self.organization_id = organization_id

    async def list_departments(self, limit: int, offset: int) -> list[Department]:
        return await self.repo.list(limit=limit, offset=offset)

    async def get_department(self, department_id: uuid.UUID) -> Department:
        department = await self.repo.get_by_id(department_id)
        if not department:
            raise NotFoundError("Department not found.")
        return department

    async def create_department(self, request: DepartmentCreateRequest) -> Department:
        department = await self.repo.create(
            Department(organization_id=self.organization_id, name=request.name)
        )
        await self.session.commit()
        return department

    async def update_department(
        self, department_id: uuid.UUID, request: DepartmentUpdateRequest
    ) -> Department:
        department = await self.get_department(department_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(department, field, value)
        await self.repo.update(department)
        await self.session.commit()
        return department

    async def delete_department(self, department_id: uuid.UUID) -> None:
        department = await self.get_department(department_id)
        await self.repo.soft_delete(department)
        await self.session.commit()
