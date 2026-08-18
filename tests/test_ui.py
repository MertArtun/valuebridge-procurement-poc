from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore


def _client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=Path.cwd(),
    )
    return TestClient(create_app(service=service))


def test_home_exposes_the_interactive_hero_flow(tmp_path: Path) -> None:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=Path.cwd(),
    )
    client = TestClient(create_app(service=service))

    response = client.get("/")

    assert response.status_code == 200
    assert "Talebi Analiz Et" in response.text
    assert "İnsan Onayını Ver" in response.text
    assert "/static/app.js" in response.text


def test_home_ships_a_region_for_every_workflow_state(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/").text

    for element_id in (
        "analysis-loading",
        "analysis-error",
        "security-notice",
        "approval-status",
        "execution-success",
        "duplicate-notice",
        "action-error",
        "audit-events",
    ):
        assert f'id="{element_id}"' in html, element_id


def test_home_labels_pending_failure_duplicate_and_quarantine_states(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/").text

    assert "ONAY BEKLİYOR" in html
    assert "Analiz başarısız" in html
    assert "ALREADY_PROCESSED" in html
    assert "SECURITY_CONTENT_QUARANTINED" in html


def test_state_regions_are_announced_and_hidden_until_used(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/").text

    for line in html.splitlines():
        if 'class="state-banner' not in line:
            continue
        assert 'role="status"' in line or 'role="alert"' in line, line
        assert "hidden" in line, line
    assert 'aria-live="polite"' in html


def test_audit_drawer_reveals_details_json_and_trace_id_on_interaction(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text

    assert "<details" in script
    assert "<summary" in script
    assert "Trace ID" in script
    assert "item.trace_id" in script
    assert "JSON.stringify(item.details" in script


def test_stylesheet_ships_keyboard_focus_styles(tmp_path: Path) -> None:
    stylesheet = _client(tmp_path).get("/static/app.css").text

    assert ":focus-visible" in stylesheet
    assert ".state-banner" in stylesheet
