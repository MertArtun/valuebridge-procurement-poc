from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from app.errors import IdempotencyConflictError, InvalidApprovalStateError
from app.mockdesk_client import InProcessMockDeskGateway
from app.models import PurchaseRequest
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]


def _concurrently(callables):
    barrier = Barrier(len(callables))

    def invoke(fn):
        barrier.wait()
        return fn()

    with ThreadPoolExecutor(max_workers=len(callables)) as executor:
        futures = [executor.submit(invoke, fn) for fn in callables]
    values = []
    errors = []
    for future in futures:
        try:
            values.append(future.result())
        except Exception as exc:
            errors.append(exc)
    return values, errors


def test_same_idempotency_key_is_atomic_under_concurrency(tmp_path: Path) -> None:
    store = MockDeskStore(tmp_path / "mockdesk.db")
    payload = {"request_id": "PR-2026-0042", "summary": "Procurement Exception Review"}
    key = "PR-2026-0042-PROCUREMENT-REVIEW"

    values, errors = _concurrently([lambda: store.create_ticket(payload, key) for _ in range(20)])

    assert errors == []
    assert store.ticket_count() == 1
    assert {value.ticket_id for value in values} == {values[0].ticket_id}
    assert sum(value.status == "OPEN" for value in values) == 1
    assert sum(value.status == "ALREADY_PROCESSED" for value in values) == 19


def test_different_idempotency_keys_never_collide_under_concurrency(tmp_path: Path) -> None:
    store = MockDeskStore(tmp_path / "mockdesk.db")
    calls = [
        lambda index=index: store.create_ticket(
            {"request_id": f"PR-{index:04d}", "summary": "Review"},
            f"KEY-{index:04d}",
        )
        for index in range(20)
    ]

    values, errors = _concurrently(calls)

    assert errors == []
    assert store.ticket_count() == 20
    assert len({value.ticket_id for value in values}) == 20


def test_same_idempotency_key_with_different_payload_is_conflict(tmp_path: Path) -> None:
    store = MockDeskStore(tmp_path / "mockdesk.db")
    key = "PR-2026-0042-PROCUREMENT-REVIEW"
    store.create_ticket({"request_id": "PR-2026-0042", "summary": "Original"}, key)

    with pytest.raises(IdempotencyConflictError):
        store.create_ticket({"request_id": "PR-2026-0042", "summary": "Changed"}, key)

    assert store.ticket_count() == 1


def test_concurrent_approve_and_reject_has_one_terminal_transition_and_audit(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "valuebridge.db")
    service = ProcurementService.from_project_data(
        store=store,
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    response = service.analyze(
        PurchaseRequest(
            request_id="PR-2026-RACE",
            request_date="2026-08-18",
            supplier_name="Atlas Endüstri",
            category="SPARE_PARTS",
            amount_try="220000",
            received_quotes=1,
            offered_lead_time_days=20,
        ),
        role="procurement_specialist",
        user="procurement_user",
    )
    assert response.approval is not None
    approval_id = response.approval.approval_id

    values, errors = _concurrently(
        [
            lambda: service.approve(
                approval_id, role="finance_approver", user="finance_approve"
            ),
            lambda: service.reject(
                approval_id, role="finance_approver", user="finance_reject"
            ),
        ]
    )

    assert len(values) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidApprovalStateError)
    assert store.get_approval(approval_id).status in {"APPROVED", "REJECTED"}
    terminal_events = [
        event
        for event in store.list_audit()
        if event.event_type in {"APPROVAL_GRANTED", "APPROVAL_REJECTED"}
    ]
    assert len(terminal_events) == 1


def test_concurrent_analyses_of_one_request_leave_one_live_approval(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "valuebridge.db")
    service = ProcurementService.from_project_data(
        store=store,
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )

    def analyze(received_quotes: int):
        return service.analyze(
            PurchaseRequest(
                request_id="PR-2026-RACE2",
                request_date="2026-08-18",
                supplier_name="Atlas Endüstri",
                category="SPARE_PARTS",
                amount_try="220000",
                received_quotes=received_quotes,
                offered_lead_time_days=20,
            ),
            role="procurement_specialist",
            user="procurement_user",
        )

    values, errors = _concurrently([lambda: analyze(1), lambda: analyze(2)])

    assert errors == []
    approval_ids = {value.approval.approval_id for value in values}
    assert len(approval_ids) == 2
    statuses = sorted(store.get_approval(approval_id).status for approval_id in approval_ids)
    assert statuses == ["PENDING", "SUPERSEDED"]
    superseded = [
        event for event in store.list_audit() if event.event_type == "APPROVAL_SUPERSEDED"
    ]
    assert len(superseded) == 1


def test_concurrent_expiry_emits_one_audit_event(tmp_path: Path) -> None:
    class Clock:
        current = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

        def __call__(self):
            return self.current

    clock = Clock()
    store = SQLiteStore(tmp_path / "valuebridge.db", now=clock)
    approval = store.create_approval("PR-EXPIRY", "WRITE", "user")
    store.save_case(approval.approval_id, {"trace_id": "trace-expiry"})
    clock.current = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

    values, errors = _concurrently(
        [lambda: store.get_approval(approval.approval_id) for _ in range(12)]
    )

    assert errors == []
    assert {value.status for value in values} == {"EXPIRED"}
    expiry_events = [
        event for event in store.list_audit() if event.event_type == "APPROVAL_EXPIRED"
    ]
    assert len(expiry_events) == 1
