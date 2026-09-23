import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.departments.schemas import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
)
from app.modules.departments.service import DepartmentService

router = APIRouter(prefix="/api/v1/departments", tags=["Departments"])


@router.get("", response_model=list[DepartmentResponse])
async def list_departments(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[DepartmentResponse]:
    departments = await DepartmentService(db, current_user.organization_id).list_departments(
        limit, offset
    )
    return [DepartmentResponse.model_validate(d) for d in departments]


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    request: DepartmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> DepartmentResponse:
    department = await DepartmentService(db, current_user.organization_id).create_department(
        request
    )
    return DepartmentResponse.model_validate(department)


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> DepartmentResponse:
    department = await DepartmentService(db, current_user.organization_id).get_department(
        department_id
    )
    return DepartmentResponse.model_validate(department)


@router.patch("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: uuid.UUID,
    request: DepartmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> DepartmentResponse:
    department = await DepartmentService(db, current_user.organization_id).update_department(
        department_id, request
    )
    return DepartmentResponse.model_validate(department)


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> None:
    await DepartmentService(db, current_user.organization_id).delete_department(department_id)
