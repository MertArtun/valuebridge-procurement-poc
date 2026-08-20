"""The intake chips are the guided tour's script.

The README claims the third chip trips the injection detector, so the chip text
and the detector have to be checked against each other, not against prose.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.security import matched_injection_rule
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
REQUEST_ID_TOKEN = "__REQUEST_ID__"
DUMMY_REQUEST_ID = "PR-DEMO-7Q2X"
CHIP_PATTERN = re.compile(
    r'id="(intake-example-[a-z-]+)"[^>]*data-example="([^"]*)"',
)


def intake_chip_examples(tmp_path: Path) -> dict[str, str]:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    html = TestClient(create_app(service=service)).get("/").text
    return dict(CHIP_PATTERN.findall(html))


def test_only_the_injection_chip_trips_an_injection_rule(tmp_path: Path) -> None:
    examples = intake_chip_examples(tmp_path)

    assert set(examples) == {
        "intake-example-single-quote",
        "intake-example-clean",
        "intake-example-injection",
    }
    matches = {
        chip_id: matched_injection_rule(text.replace(REQUEST_ID_TOKEN, DUMMY_REQUEST_ID))
        for chip_id, text in examples.items()
    }

    assert matches == {
        "intake-example-single-quote": None,
        "intake-example-clean": None,
        "intake-example-injection": "INSTRUCTION_OVERRIDE_TR",
    }


def test_every_intake_chip_carries_the_session_request_token(tmp_path: Path) -> None:
    examples = intake_chip_examples(tmp_path)

    for chip_id, text in examples.items():
        assert REQUEST_ID_TOKEN in text, chip_id


def test_every_intake_chip_states_the_fields_the_form_requires(tmp_path: Path) -> None:
    examples = intake_chip_examples(tmp_path)

    for chip_id, text in examples.items():
        assert "2026" in text, chip_id
        assert "TL" in text, chip_id
        assert "teklif" in text, chip_id
        assert "teslim" in text, chip_id
