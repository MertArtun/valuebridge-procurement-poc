from pathlib import Path

import pytest

from app.security import AuthorizationError, authorize, contains_prompt_injection


def test_supplier_attachment_prompt_injection_is_detected() -> None:
    text = Path("data/supplier_attachment_untrusted.md").read_text(encoding="utf-8")

    assert contains_prompt_injection(text) is True


def test_only_finance_approver_can_approve_finance_action() -> None:
    with pytest.raises(AuthorizationError):
        authorize(role="procurement_specialist", action="approve_finance_action")

    authorize(role="finance_approver", action="approve_finance_action")
