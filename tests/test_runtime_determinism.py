from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]


def build_client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


def test_docs_ui_is_not_blocked_by_csp(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    docs = client.get("/docs")
    schema = client.get("/openapi.json")
    home = client.get("/")

    assert docs.status_code == 200
    assert "Content-Security-Policy" not in docs.headers
    assert schema.status_code == 200
    assert "Content-Security-Policy" not in schema.headers
    assert "default-src 'self'" in home.headers["Content-Security-Policy"]


def test_routes_resolve_default_service_without_lifespan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VALUEBRIDGE_DB_PATH", str(tmp_path / "default.db"))
    client = TestClient(create_app())  # no context manager: lifespan never runs

    response = client.get(
        "/api/v1/audit/events",
        headers={"X-Demo-Role": "solution_engineer", "X-Demo-User": "solution_engineer"},
    )

    assert response.status_code == 200
    assert response.json() == []
