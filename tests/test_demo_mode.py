from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

AUDIT_HEADERS = {"X-Demo-Role": "auditor", "X-Demo-User": "auditor_user"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def build_client(tmp_path: Path, **app_options) -> TestClient:
    store = SQLiteStore(tmp_path / "valuebridge.db")
    mockdesk = InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db"))
    service = ProcurementService.from_project_data(
        store=store,
        mockdesk_gateway=mockdesk,
        project_root=Path.cwd(),
    )
    return TestClient(create_app(service=service, **app_options))


def test_disabled_demo_mode_sends_no_robots_header(tmp_path: Path) -> None:
    client = build_client(tmp_path, demo_mode=False)

    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Robots-Tag" not in response.headers


def test_disabled_demo_mode_does_not_rate_limit_the_api(tmp_path: Path) -> None:
    client = build_client(tmp_path, demo_mode=False)

    statuses = {
        client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code
        for _ in range(35)
    }

    assert statuses == {200}


def test_demo_mode_marks_every_response_as_noindex(tmp_path: Path) -> None:
    client = build_client(tmp_path, demo_mode=True)

    assert client.get("/health").headers["X-Robots-Tag"] == "noindex, nofollow"
    assert client.get("/").headers["X-Robots-Tag"] == "noindex, nofollow"


def test_demo_mode_is_enabled_by_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VALUEBRIDGE_DEMO_MODE", "1")

    client = build_client(tmp_path)

    assert client.get("/health").headers["X-Robots-Tag"] == "noindex, nofollow"


def test_demo_mode_stays_off_for_other_environment_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VALUEBRIDGE_DEMO_MODE", "true")

    client = build_client(tmp_path)

    assert "X-Robots-Tag" not in client.get("/health").headers


def test_demo_mode_rejects_api_calls_beyond_the_bucket_capacity(tmp_path: Path) -> None:
    clock = FakeClock()
    client = build_client(tmp_path, demo_mode=True, clock=clock)

    allowed = [
        client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code
        for _ in range(30)
    ]
    limited = client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS)

    assert set(allowed) == {200}
    assert limited.status_code == 429
    assert limited.json() == {
        "error": {
            "code": "RATE_LIMITED",
            "message": limited.json()["error"]["message"],
            "trace_id": None,
            "retryable": True,
        }
    }
    assert limited.json()["error"]["message"]
    assert int(limited.headers["Retry-After"]) == 2
    assert limited.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_demo_mode_does_not_rate_limit_non_api_paths(tmp_path: Path) -> None:
    clock = FakeClock()
    client = build_client(tmp_path, demo_mode=True, clock=clock)

    statuses = {client.get("/health").status_code for _ in range(35)}

    assert statuses == {200}


def test_forwarded_clients_get_independent_buckets(tmp_path: Path) -> None:
    clock = FakeClock()
    client = build_client(tmp_path, demo_mode=True, clock=clock)
    first = dict(AUDIT_HEADERS, **{"X-Forwarded-For": "203.0.113.7, 10.0.0.1"})
    second = dict(AUDIT_HEADERS, **{"X-Forwarded-For": "198.51.100.4"})

    for _ in range(30):
        assert client.get("/api/v1/metrics/summary", headers=first).status_code == 200

    assert client.get("/api/v1/metrics/summary", headers=first).status_code == 429
    assert client.get("/api/v1/metrics/summary", headers=second).status_code == 200


def test_bucket_refills_as_time_advances(tmp_path: Path) -> None:
    clock = FakeClock()
    client = build_client(tmp_path, demo_mode=True, clock=clock)
    for _ in range(30):
        client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS)

    assert client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code == 429

    clock.advance(2)

    assert client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code == 200
    assert client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code == 429

    clock.advance(600)

    statuses = {
        client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code
        for _ in range(30)
    }
    assert statuses == {200}
