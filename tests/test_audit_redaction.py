"""The public demo shows its whole audit trail to every visitor.

Free-text questions therefore have to be reducible to a length before they are
written down, without changing what a private deployment records.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app import main
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "Finans yöneticisi onayı hangi tutarın üzerinde gerekir?"
ASKED_ON = date(2026, 8, 18)


@pytest.fixture(autouse=True)
def redaction_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VALUEBRIDGE_REDACT_QA_AUDIT", raising=False)


def build_service(tmp_path: Path, *, redact: bool) -> ProcurementService:
    return ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
        redact_question_audit=redact,
    )


def ask(service: ProcurementService) -> None:
    service.ask_policy_question(
        QUESTION,
        ASKED_ON,
        role="procurement_specialist",
        user="procurement_user",
    )


def policy_qa_details(service: ProcurementService) -> dict:
    ask(service)
    asked = [item for item in service.store.list_audit() if item.event_type == "POLICY_QA"]
    assert len(asked) == 1
    return asked[0].details


def test_redaction_records_a_length_instead_of_the_question(tmp_path: Path) -> None:
    details = policy_qa_details(build_service(tmp_path, redact=True))

    assert "question" not in details
    assert details["question_length"] == len(QUESTION)


def test_redaction_keeps_every_field_an_auditor_needs(tmp_path: Path) -> None:
    details = policy_qa_details(build_service(tmp_path, redact=True))

    assert details["retrieval_mode"] in {"lexical", "hybrid"}
    assert details["section_ids"]
    assert details["injection_rule_id"] is None


def test_redaction_leaves_no_question_text_anywhere_in_the_trail(tmp_path: Path) -> None:
    service = build_service(tmp_path, redact=True)
    ask(service)

    trail = json.dumps(
        [event.model_dump(mode="json") for event in service.store.list_audit()],
        ensure_ascii=False,
    )

    assert "tutarın üzerinde" not in trail


def test_a_private_deployment_still_records_the_question(tmp_path: Path) -> None:
    details = policy_qa_details(build_service(tmp_path, redact=False))

    assert details["question"] == QUESTION
    assert "question_length" not in details


def test_the_default_service_reads_the_flag_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VALUEBRIDGE_DB_PATH", str(tmp_path / "valuebridge.db"))

    assert main._default_service().redact_question_audit is False

    monkeypatch.setenv("VALUEBRIDGE_REDACT_QA_AUDIT", "1")

    assert main._default_service().redact_question_audit is True
