import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.automation.schemas import (
    AutomationRuleCreateRequest,
    AutomationRuleResponse,
    AutomationRuleUpdateRequest,
)
from app.modules.automation.service import AutomationRuleService

router = APIRouter(prefix="/api/v1/automation-rules", tags=["Automation"])


@router.get("", response_model=list[AutomationRuleResponse])
async def list_rules(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[AutomationRuleResponse]:
    rules = await AutomationRuleService(db, current_user.organization_id).list_rules(limit, offset)
    return [AutomationRuleResponse.model_validate(r) for r in rules]


@router.post("", response_model=AutomationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    request: AutomationRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> AutomationRuleResponse:
    rule = await AutomationRuleService(db, current_user.organization_id).create_rule(request)
    return AutomationRuleResponse.model_validate(rule)


@router.patch("/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    request: AutomationRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> AutomationRuleResponse:
    rule = await AutomationRuleService(db, current_user.organization_id).update_rule(
        rule_id, request
    )
    return AutomationRuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
) -> None:
    await AutomationRuleService(db, current_user.organization_id).delete_rule(rule_id)
