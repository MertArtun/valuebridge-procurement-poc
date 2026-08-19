from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.errors import IdempotencyConflictError
from app.mockdesk_client import InProcessMockDeskGateway
from app.models import TicketResult
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]


def test_mockdesk_package_does_not_import_the_app_package() -> None:
    offenders: list[str] = []
    for module in sorted((ROOT / "mockdesk").glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders.extend(
                    f"{module.name}: import {alias.name}"
                    for alias in node.names
                    if alias.name == "app" or alias.name.startswith("app.")
                )
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "app" or node.module.startswith("app.")):
                    offenders.append(f"{module.name}: from {node.module} import ...")
    assert offenders == []


def test_http_conflict_keeps_the_error_contract(tmp_path: Path, monkeypatch) -> None:
    import mockdesk.main as mockdesk_main

    monkeypatch.setattr(mockdesk_main, "store", MockDeskStore(tmp_path / "mockdesk.db"))
    client = TestClient(mockdesk_main.app)

    first = client.post(
        "/tickets",
        json={"request_id": "PR-2026-0042", "summary": "Review"},
        headers={"Idempotency-Key": "K-CONTRACT"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "OPEN"

    conflict = client.post(
        "/tickets",
        json={"request_id": "PR-2026-0042", "summary": "Changed"},
        headers={"Idempotency-Key": "K-CONTRACT"},
    )
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "IDEMPOTENCY_CONFLICT"
    assert error["retryable"] is False
    assert error["message"]


def test_in_process_gateway_translates_results_and_conflicts(tmp_path: Path) -> None:
    gateway = InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db"))

    result = gateway.create_ticket({"request_id": "PR-2026-0042"}, idempotency_key="K-GW")

    assert isinstance(result, TicketResult)
    assert result.status == "OPEN"
    assert result.request_id == "PR-2026-0042"

    replay = gateway.create_ticket({"request_id": "PR-2026-0042"}, idempotency_key="K-GW")
    assert replay.status == "ALREADY_PROCESSED"

    with pytest.raises(IdempotencyConflictError):
        gateway.create_ticket({"request_id": "PR-OTHER"}, idempotency_key="K-GW")
