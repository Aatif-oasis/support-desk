from sqlalchemy import select

from app.modules.automation.models import AutomationRule
from app.shared.base_repository import BaseRepository


class AutomationRuleRepository(BaseRepository[AutomationRule]):
    model = AutomationRule

    async def list_active_by_trigger(self, trigger_event: str) -> list[AutomationRule]:
        query = self._base_query().where(
            AutomationRule.trigger_event == trigger_event, AutomationRule.is_active.is_(True)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
