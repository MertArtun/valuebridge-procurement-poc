from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
AUDIT_HEADERS = {"X-Demo-Role": "auditor", "X-Demo-User": "auditor_user"}
STATUS_KEYS = {
    "status",
    "build_sha",
    "llm_enabled",
    "embedding_index_present",
    "demo_mode",
    "mockdesk_reachable",
}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def closed_mockdesk_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing listens on port 1, so the probe fails fast instead of resolving DNS."""
    monkeypatch.setenv("MOCKDESK_URL", "http://127.0.0.1:1")
    monkeypatch.delenv("VALUEBRIDGE_BUILD_SHA", raising=False)


def build_client(tmp_path: Path, **app_options) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service, **app_options))


def test_status_answers_without_a_role_header(tmp_path: Path) -> None:
    response = build_client(tmp_path).get("/api/v1/status")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == STATUS_KEYS
    assert body["status"] == "ok"


def test_status_reports_the_build_sha_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert build_client(tmp_path).get("/api/v1/status").json()["build_sha"] == "dev"

    monkeypatch.setenv("VALUEBRIDGE_BUILD_SHA", "9f3c1ab")

    assert build_client(tmp_path).get("/api/v1/status").json()["build_sha"] == "9f3c1ab"


def test_status_reports_the_model_and_index_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "_EMBEDDINGS_INDEX", tmp_path / "absent.json")
    keyless = build_client(tmp_path).get("/api/v1/status").json()

    assert keyless["llm_enabled"] is False
    assert keyless["embedding_index_present"] is False

    monkeypatch.setenv("VALUEBRIDGE_LLM_API_KEY", "test-key")
    index = tmp_path / "present.json"
    index.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main, "_EMBEDDINGS_INDEX", index)
    configured = build_client(tmp_path).get("/api/v1/status").json()

    assert configured["llm_enabled"] is True
    assert configured["embedding_index_present"] is True


def test_status_reports_whether_the_demo_profile_is_on(tmp_path: Path) -> None:
    def demo_mode_flag(enabled: bool) -> bool:
        client = build_client(tmp_path, demo_mode=enabled)
        return client.get("/api/v1/status").json()["demo_mode"]

    assert demo_mode_flag(False) is False
    assert demo_mode_flag(True) is True


def test_status_reports_an_unreachable_gateway_without_raising(tmp_path: Path) -> None:
    response = build_client(tmp_path).get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["mockdesk_reachable"] is False


def test_status_never_echoes_a_secret_a_model_name_or_a_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VALUEBRIDGE_LLM_API_KEY", "sk-super-secret")
    monkeypatch.setenv("VALUEBRIDGE_LLM_MODEL", "anthropic/claude-haiku-4.5")

    text = build_client(tmp_path).get("/api/v1/status").text

    assert "sk-super-secret" not in text
    assert "claude" not in text
    assert "http" not in text


def test_status_is_exempt_from_the_demo_rate_limit(tmp_path: Path) -> None:
    client = build_client(tmp_path, demo_mode=True, clock=FakeClock())

    statuses = {client.get("/api/v1/status").status_code for _ in range(35)}

    assert statuses == {200}
    # The bucket is untouched, so a limited path still gets its full capacity.
    allowed = [
        client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code
        for _ in range(30)
    ]
    assert set(allowed) == {200}
    assert client.get("/api/v1/metrics/summary", headers=AUDIT_HEADERS).status_code == 429
