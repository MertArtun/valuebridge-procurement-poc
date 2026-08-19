from __future__ import annotations

import re

from app.errors import AuthorizationError

_ACTION_ROLES: dict[str, set[str]] = {
    "analyze_request": {"procurement_specialist", "solution_engineer"},
    "approve_finance_action": {"finance_approver"},
    "view_action_preview": {"procurement_specialist", "finance_approver", "solution_engineer"},
    "execute_tool_action": {"procurement_specialist", "solution_engineer"},
    "read_audit": {"auditor", "solution_engineer", "finance_approver"},
    "draft_intake_request": {"procurement_specialist", "solution_engineer"},
    "ask_policy_question": {
        "procurement_specialist",
        "finance_approver",
        "auditor",
        "solution_engineer",
    },
}

_INJECTION_RULES: dict[str, re.Pattern[str]] = {
    rule_id: re.compile(pattern, re.IGNORECASE)
    for rule_id, pattern in (
        ("INSTRUCTION_OVERRIDE_TR", r"önceki\s+(tüm\s+)?talimatları\s+(yok say|görmezden gel)"),
        ("INSTRUCTION_OVERRIDE_EN", r"ignore\s+(all\s+)?previous\s+instructions"),
        ("SECRET_DISCLOSURE_TR", r"api\s+anahtarlarını\s+göster"),
        ("SECRET_DISCLOSURE_EN", r"show\s+(the\s+)?api\s+keys"),
        ("SYSTEM_PROMPT_PROBE", r"system\s+(prompt|variables)"),
    )
}


def authorize(role: str, action: str) -> None:
    allowed = _ACTION_ROLES.get(action, set())
    if role not in allowed:
        raise AuthorizationError(f"Role {role!r} is not authorized for {action!r}")


def matched_injection_rule(text: str) -> str | None:
    """Return the identifier of the first matching injection rule, never the matched text."""
    for rule_id, pattern in _INJECTION_RULES.items():
        if pattern.search(text):
            return rule_id
    return None


def contains_prompt_injection(text: str) -> bool:
    return matched_injection_rule(text) is not None
