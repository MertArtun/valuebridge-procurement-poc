from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.llm_benchmark import (
    ABSTENTION_SENTENCE,
    INTAKE_FIELDS,
    build_report,
    field_accuracy,
    format_comparison_table,
    groundedness,
    is_abstention,
    load_intake_cases,
    load_qa_cases,
    run_intake_suite,
    run_qa_suite,
    score_intake_fields,
    top1_hit,
)
from app.models import PurchaseRequestDraft
from app.policy_qa import PolicyQaService
from app.retrieval import PolicyRepository

ROOT = Path(__file__).resolve().parents[1]
INTAKE_PATH = ROOT / "evals/benchmarks/intake_benchmark.jsonl"
QA_PATH = ROOT / "evals/benchmarks/qa_benchmark.jsonl"
DOCUMENTS_PATH = ROOT / "data/documents.json"
SUPPLIERS_PATH = ROOT / "data/suppliers.csv"
BENCHMARK_ROLE = "procurement_specialist"


class SequenceChatClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.responses[len(self.calls) - 1]


class FixedChatClient:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, *, system: str, user: str) -> str:
        del system, user
        return self.response


def test_intake_benchmark_dataset_is_schema_valid() -> None:
    cases = load_intake_cases(INTAKE_PATH)

    assert len(cases) == 15
    assert len({case.case_id for case in cases}) == 15
    assert all(isinstance(case.expected, PurchaseRequestDraft) for case in cases)
    assert all(case.text.strip() for case in cases)


def test_intake_benchmark_covers_partial_irrelevant_and_known_suppliers() -> None:
    cases = load_intake_cases(INTAKE_PATH)
    known = {
        line.split(",")[0]
        for line in SUPPLIERS_PATH.read_text(encoding="utf-8").splitlines()[1:]
        if line.strip()
    }

    null_counts = [
        sum(1 for name in INTAKE_FIELDS if getattr(case.expected, name) is None) for case in cases
    ]
    assert null_counts.count(0) >= 8
    assert any(0 < count < len(INTAKE_FIELDS) for count in null_counts)
    assert null_counts.count(len(INTAKE_FIELDS)) == 1

    suppliers = {case.expected.supplier_name for case in cases} - {None}
    assert suppliers <= known


def test_intake_benchmark_includes_injection_cases_with_clean_expectations() -> None:
    cases = {case.case_id: case for case in load_intake_cases(INTAKE_PATH)}

    injected = [
        case
        for case in cases.values()
        if "yok say" in case.text or "Sistem notu" in case.text
    ]
    assert len(injected) >= 2
    for case in injected:
        assert case.expected.supplier_name in {"Nova Rulman", "Ege Parça"}
        assert case.expected.amount_try is not None


def test_qa_benchmark_dataset_is_schema_valid() -> None:
    cases = load_qa_cases(QA_PATH)
    repository = PolicyRepository(DOCUMENTS_PATH)
    sections = {
        (document.document_id, section.section_id)
        for document in repository.searchable_documents(BENCHMARK_ROLE)
        for section in document.sections
    }

    assert len(cases) == 15
    assert len({case.case_id for case in cases}) == 15
    for case in cases:
        assert case.abstain == (case.expected_section is None)
        assert case.must_contain
        assert case.on_date == date(2026, 8, 18)
        if case.expected_section is not None:
            assert case.expected_section in sections
        else:
            assert case.must_contain == (ABSTENTION_SENTENCE,)

    assert sum(1 for case in cases if case.abstain) == 3


def test_qa_loader_rejects_an_inconsistent_abstain_flag(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_id": "QAB-900",
                "question": "Soru",
                "on_date": "2026-08-18",
                "expected": {
                    "top_section": {"document_id": "PROC-POL-2026", "section_id": "4.2"},
                    "must_contain": ["§4.2"],
                    "abstain": True,
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="QAB-900"):
        load_qa_cases(path)


def test_score_intake_fields_marks_exact_and_missed_fields() -> None:
    expected = PurchaseRequestDraft(
        request_id="PR-2026-0042",
        request_date=date(2026, 8, 18),
        supplier_name="Atlas Endüstri",
        category="SPARE_PARTS",
        amount_try=Decimal("220000"),
        received_quotes=1,
        offered_lead_time_days=20,
    )

    assert field_accuracy(score_intake_fields(expected, expected)) == 1.0

    actual = expected.model_copy(update={"received_quotes": 2, "supplier_name": "Ege Parça"})
    matches = score_intake_fields(expected, actual)
    assert matches["received_quotes"] is False
    assert matches["supplier_name"] is False
    assert matches["amount_try"] is True
    assert field_accuracy(matches) == pytest.approx(5 / 7)


def test_score_intake_fields_requires_null_where_null_is_expected() -> None:
    expected = PurchaseRequestDraft(supplier_name="Mavi Teknik", category="SPARE_PARTS")
    invented = expected.model_copy(update={"received_quotes": 2})

    assert field_accuracy(score_intake_fields(expected, expected)) == 1.0
    assert score_intake_fields(expected, invented)["received_quotes"] is False


def test_score_intake_fields_ignores_amount_scale() -> None:
    expected = PurchaseRequestDraft(amount_try=Decimal("220000"))
    scaled = PurchaseRequestDraft(amount_try=Decimal("220000.00"))

    assert score_intake_fields(expected, scaled)["amount_try"] is True


def test_run_intake_suite_scores_a_mini_run() -> None:
    cases = load_intake_cases(INTAKE_PATH)[:2]
    second = cases[1].expected.model_copy(update={"received_quotes": 9})
    client = SequenceChatClient(
        [
            f"```json\n{cases[0].expected.model_dump_json(by_alias=True)}\n```",
            second.model_dump_json(by_alias=True),
        ]
    )

    result = run_intake_suite(cases, client)

    assert result["parse_failures"] == 0
    assert result["perfect_cases"] == 1
    assert result["mean_field_accuracy"] == pytest.approx((1.0 + 6 / 7) / 2, abs=1e-4)
    assert [entry["case_id"] for entry in result["per_case"]] == ["INTB-001", "INTB-002"]
    assert result["per_case"][1]["fields"]["received_quotes"] is False
    assert result["p50_ms"] >= 0.0
    assert result["p95_ms"] >= result["p50_ms"]


def test_run_intake_suite_counts_an_unparseable_completion() -> None:
    cases = load_intake_cases(INTAKE_PATH)[:1]

    result = run_intake_suite(cases, FixedChatClient("Tabii, işte taslak: yedek parça"))

    assert result["parse_failures"] == 1
    assert result["perfect_cases"] == 0
    assert result["mean_field_accuracy"] == 0.0
    assert result["per_case"][0]["parsed"] is False
    assert result["per_case"][0]["error"]


def test_is_abstention_accepts_the_sentence_or_an_empty_retrieval() -> None:
    assert is_abstention(f"{ABSTENTION_SENTENCE}", []) is True
    assert is_abstention(None, []) is True
    assert is_abstention(None, [{"document_id": "PROC-POL-2026", "section_id": "4.2"}]) is False
    assert is_abstention("200.000 TL üzeri finans onayı gerektirir (§4.2).", []) is False


def test_top1_hit_compares_the_first_ranked_section() -> None:
    cases = {case.case_id: case for case in load_qa_cases(QA_PATH)}
    sections = [
        {"document_id": "PROC-POL-2026", "section_id": "4.2"},
        {"document_id": "PROC-POL-2026", "section_id": "4.3"},
    ]

    assert top1_hit(cases["QAB-001"], sections, "cevap") is True
    assert top1_hit(cases["QAB-003"], sections, "cevap") is False
    assert top1_hit(cases["QAB-001"], [], None) is False
    assert top1_hit(cases["QAB-013"], sections, ABSTENTION_SENTENCE) is True
    assert top1_hit(cases["QAB-013"], sections, "Yıllık izin 14 gündür.") is False


def test_groundedness_is_the_share_of_required_strings() -> None:
    assert groundedness(("200.000", "§4.2"), "200.000 TL üzeri onay gerektirir (§4.2).") == 1.0
    assert groundedness(("200.000", "§4.2"), "200.000 TL üzeri onay gerektirir.") == 0.5
    assert groundedness(("finans",), "FINANS onayı gerektirir.") == 1.0
    assert groundedness(("§4.2",), None) == 0.0


def test_run_qa_suite_scores_a_mini_run_against_the_real_corpus() -> None:
    cases = [case for case in load_qa_cases(QA_PATH) if case.case_id in {"QAB-001", "QAB-013"}]
    service = PolicyQaService(
        PolicyRepository(DOCUMENTS_PATH),
        chat_client=SequenceChatClient(
            [
                "200.000 TL üzerindeki talepler finans onayı gerektirir (§4.2).",
                ABSTENTION_SENTENCE,
            ]
        ),
    )

    result = run_qa_suite(cases, service)

    assert result["top1_accuracy"] == 1.0
    assert result["groundedness"] == 1.0
    assert result["abstain_accuracy"] == 1.0
    assert [entry["case_id"] for entry in result["per_case"]] == ["QAB-001", "QAB-013"]
    assert result["per_case"][0]["top_section"] == {
        "document_id": "PROC-POL-2026",
        "section_id": "4.2",
    }
    assert result["per_case"][0]["retrieval_mode"] == "lexical"
    assert result["per_case"][1]["abstained"] is True


def test_run_qa_suite_penalises_an_ungrounded_answer() -> None:
    cases = [case for case in load_qa_cases(QA_PATH) if case.case_id == "QAB-013"]
    service = PolicyQaService(
        PolicyRepository(DOCUMENTS_PATH),
        chat_client=FixedChatClient("Yıllık izin hakkı 14 gündür."),
    )

    result = run_qa_suite(cases, service)

    assert result["abstain_accuracy"] == 0.0
    assert result["groundedness"] == 0.0
    assert result["top1_accuracy"] == 0.0


def test_build_report_and_table_carry_every_model() -> None:
    intake_cases = load_intake_cases(INTAKE_PATH)[:1]
    qa_cases = [case for case in load_qa_cases(QA_PATH) if case.case_id == "QAB-001"]
    service = PolicyQaService(
        PolicyRepository(DOCUMENTS_PATH),
        chat_client=FixedChatClient("200.000 TL üzeri finans onayı gerektirir (§4.2)."),
    )
    entry = {
        "model": "vendor/model-a",
        "intake": run_intake_suite(
            intake_cases,
            FixedChatClient(intake_cases[0].expected.model_dump_json(by_alias=True)),
        ),
        "qa": run_qa_suite(qa_cases, service),
    }

    report = build_report([entry])

    assert report["generated_at"].endswith("+00:00")
    assert [model["model"] for model in report["models"]] == ["vendor/model-a"]
    assert report["models"][0]["intake"]["mean_field_accuracy"] == 1.0

    table = format_comparison_table(report)
    assert "vendor/model-a" in table
    assert "intake.mean_field_accuracy" in table
    assert "qa.top1_accuracy" in table
    assert json.loads(json.dumps(report))["models"][0]["qa"]["per_case"][0]["case_id"] == "QAB-001"


def test_cli_without_an_api_key_fails_with_a_clear_message() -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VALUEBRIDGE_")
    }

    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_llm_benchmark.py")],
        capture_output=True,
        text=True,
        env=environment,
        cwd=ROOT,
    )

    assert completed.returncode == 1
    assert "VALUEBRIDGE_LLM_API_KEY" in completed.stderr
