from pathlib import Path

from mockdesk.store import MockDeskStore


def test_same_idempotency_key_does_not_create_duplicate_ticket(tmp_path: Path) -> None:
    store = MockDeskStore(tmp_path / "mockdesk.db")
    payload = {
        "request_id": "PR-2026-0042",
        "summary": "Procurement Exception Review",
    }

    first = store.create_ticket(payload, idempotency_key="PR-2026-0042-PROCUREMENT-REVIEW")
    second = store.create_ticket(payload, idempotency_key="PR-2026-0042-PROCUREMENT-REVIEW")

    assert first.ticket_id == second.ticket_id
    assert first.duplicate_created is False
    assert second.duplicate_created is False
    assert second.status == "ALREADY_PROCESSED"
    assert store.ticket_count() == 1
