"""
Pure functions only: given rules and a context dict, decide which actions
fire. Deliberately has zero knowledge of Conversation/Message/Tag models —
the caller (ConversationService) owns executing actions with its own
repositories. This one-directional dependency (conversations -> automation,
never the reverse) is what keeps this module addable without touching
anything it triggers off of.
"""
from app.modules.automation.models import AutomationRule

_OPERATORS = {
    "contains": lambda field_value, target: target.lower() in str(field_value).lower(),
    "equals": lambda field_value, target: str(field_value).lower() == str(target).lower(),
    "starts_with": lambda field_value, target: str(field_value).lower().startswith(target.lower()),
}


def _condition_matches(condition: dict, context: dict) -> bool:
    field = condition.get("field")
    operator = condition.get("operator")
    target = condition.get("value")
    if field not in context or operator not in _OPERATORS:
        return False
    return _OPERATORS[operator](context[field], target)


def rule_matches(rule: AutomationRule, context: dict) -> bool:
    """Empty conditions list = always matches (unconditional automation)."""
    return all(_condition_matches(c, context) for c in rule.conditions)


def collect_actions(rules: list[AutomationRule], context: dict) -> list[dict]:
    """Returns every action from every matching rule, in rule order."""
    actions: list[dict] = []
    for rule in rules:
        if rule_matches(rule, context):
            actions.extend(rule.actions)
    return actions
