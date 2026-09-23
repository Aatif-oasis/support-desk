import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.automation.models import AutomationRule
from app.modules.automation.repository import AutomationRuleRepository
from app.modules.automation.schemas import AutomationRuleCreateRequest, AutomationRuleUpdateRequest


class AutomationRuleService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = AutomationRuleRepository(session, organization_id=organization_id)

    async def list_rules(self, limit: int, offset: int) -> list[AutomationRule]:
        return await self.repo.list(limit=limit, offset=offset)

    async def create_rule(self, request: AutomationRuleCreateRequest) -> AutomationRule:
        rule = await self.repo.create(
            AutomationRule(
                organization_id=self.organization_id,
                name=request.name,
                trigger_event=request.trigger_event,
                conditions=request.conditions,
                actions=request.actions,
                is_active=request.is_active,
            )
        )
        await self.session.commit()
        return rule

    async def update_rule(
        self, rule_id: uuid.UUID, request: AutomationRuleUpdateRequest
    ) -> AutomationRule:
        rule = await self._get_or_404(rule_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        await self.repo.update(rule)
        await self.session.commit()
        return rule

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        rule = await self._get_or_404(rule_id)
        await self.repo.soft_delete(rule)
        await self.session.commit()

    async def _get_or_404(self, rule_id: uuid.UUID) -> AutomationRule:
        rule = await self.repo.get_by_id(rule_id)
        if not rule:
            raise NotFoundError("Automation rule not found.")
        return rule
