from pathlib import Path

import pytest

from app.approvals import ApprovalRequiredError
from app.store import SQLiteStore


def test_write_action_cannot_be_authorized_before_explicit_approval(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "valuebridge.db")
    approval = store.create_approval(
        request_id="PR-2026-0042",
        action_type="CREATE_PROCUREMENT_EXCEPTION_TICKET",
        requested_by="procurement_user",
    )

    with pytest.raises(ApprovalRequiredError):
        store.require_approved(approval.approval_id)

    store.approve(
        approval_id=approval.approval_id,
        approved_by="finance_user",
        approver_role="finance_approver",
    )
    approved = store.require_approved(approval.approval_id)

    assert approved.status == "APPROVED"
