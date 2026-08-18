from __future__ import annotations

import re


class AuthorizationError(PermissionError):
    pass


_ACTION_ROLES: dict[str, set[str]] = {
    "analyze_request": {"procurement_specialist", "solution_engineer"},
    "approve_finance_action": {"finance_approver"},
    "execute_tool_action": {"procurement_specialist", "solution_engineer"},
    "read_audit": {"auditor", "solution_engineer", "finance_approver"},
}

_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"önceki\s+(tüm\s+)?talimatları\s+(yok say|görmezden gel)",
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"api\s+anahtarlarını\s+göster",
        r"show\s+(the\s+)?api\s+keys",
        r"system\s+(prompt|variables)",
    )
]


def authorize(role: str, action: str) -> None:
    allowed = _ACTION_ROLES.get(action, set())
    if role not in allowed:
        raise AuthorizationError(f"Role {role!r} is not authorized for {action!r}")


def contains_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)
