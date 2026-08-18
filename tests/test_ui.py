from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore


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
