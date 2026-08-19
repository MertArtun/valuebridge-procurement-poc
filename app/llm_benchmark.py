"""LLM quality benchmark: scores live intake extraction and policy answering.

Unlike the frozen evaluation families in ``app/evaluation.py``, these cases need
a provider, so the harness never runs in CI. The scoring itself is deterministic
and keyless: only the two suite runners touch a client.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.errors import ValueBridgeError
from app.llm import ChatClient, load_prompt
from app.models import PurchaseRequestDraft
from app.policy_qa import PolicyQaService
from app.service import parse_intake_draft

ABSTENTION_SENTENCE = "Bu bilgi politika korpusunda yok."
INTAKE_FIELDS = tuple(PurchaseRequestDraft.model_fields)
BENCHMARK_ROLE = "procurement_specialist"

_TABLE_ROWS = (
    ("intake", "mean_field_accuracy", "{:.3f}"),
    ("intake", "perfect_cases", "{:d}"),
    ("intake", "parse_failures", "{:d}"),
    ("intake", "p50_ms", "{:.1f}"),
    ("intake", "p95_ms", "{:.1f}"),
    ("qa", "top1_accuracy", "{:.3f}"),
    ("qa", "groundedness", "{:.3f}"),
    ("qa", "abstain_accuracy", "{:.3f}"),
    ("qa", "p50_ms", "{:.1f}"),
    ("qa", "p95_ms", "{:.1f}"),
)


@dataclass(frozen=True)
class IntakeCase:
    case_id: str
    text: str
    expected: PurchaseRequestDraft


@dataclass(frozen=True)
class QaCase:
    case_id: str
    question: str
    on_date: date
    expected_section: tuple[str, str] | None
    must_contain: tuple[str, ...]
    abstain: bool


def load_intake_cases(path: Path) -> list[IntakeCase]:
    return [
        IntakeCase(
            case_id=str(payload["case_id"]),
            text=str(payload["text"]),
            expected=PurchaseRequestDraft.model_validate(payload["expected"]),
        )
        for payload in _read_jsonl(path)
    ]


def load_qa_cases(path: Path) -> list[QaCase]:
    cases: list[QaCase] = []
    for payload in _read_jsonl(path):
        case_id = str(payload["case_id"])
        expected = payload["expected"]
        section = expected.get("top_section")
        abstain = bool(expected.get("abstain", False))
        if abstain != (section is None):
            raise ValueError(
                f"{case_id}: abstain is {abstain} but top_section is "
                f"{'absent' if section is None else 'present'}"
            )
        cases.append(
            QaCase(
                case_id=case_id,
                question=str(payload["question"]),
                on_date=date.fromisoformat(str(payload["on_date"])),
                expected_section=(
                    None
                    if section is None
                    else (str(section["document_id"]), str(section["section_id"]))
                ),
                must_contain=tuple(str(item) for item in expected["must_contain"]),
                abstain=abstain,
            )
        )
    return cases


def score_intake_fields(
    expected: PurchaseRequestDraft,
    actual: PurchaseRequestDraft,
) -> dict[str, bool]:
    return {name: getattr(actual, name) == getattr(expected, name) for name in INTAKE_FIELDS}


def field_accuracy(matches: dict[str, bool]) -> float:
    return sum(1 for matched in matches.values() if matched) / len(INTAKE_FIELDS)


def is_abstention(answer: str | None, sections: list[dict[str, object]]) -> bool:
    if answer is None:
        # Governed retrieval kept nothing, so the system abstained before the
        # model was ever asked; that is the same refusal, one layer earlier.
        return not sections
    return ABSTENTION_SENTENCE.casefold() in answer.casefold()


def top1_hit(case: QaCase, sections: list[dict[str, object]], answer: str | None) -> bool:
    if case.abstain:
        return is_abstention(answer, sections)
    if not sections:
        return False
    top = sections[0]
    return (str(top["document_id"]), str(top["section_id"])) == case.expected_section


def groundedness(must_contain: tuple[str, ...], answer: str | None) -> float:
    if not must_contain:
        return 1.0
    if answer is None:
        return 0.0
    folded = answer.casefold()
    return sum(1 for item in must_contain if item.casefold() in folded) / len(must_contain)


def run_intake_suite(cases: list[IntakeCase], client: ChatClient) -> dict[str, object]:
    system = load_prompt("intake_system")
    per_case: list[dict[str, object]] = []
    for case in cases:
        started = time.monotonic()
        error: str | None = None
        draft: PurchaseRequestDraft | None = None
        try:
            completion = client.complete(system=system, user=case.text)
        except ValueBridgeError as exc:
            latency_ms = (time.monotonic() - started) * 1000
            error = exc.code
        else:
            latency_ms = (time.monotonic() - started) * 1000
            try:
                draft = parse_intake_draft(completion)
            except ValueBridgeError as exc:
                error = exc.code
        matches = (
            {name: False for name in INTAKE_FIELDS}
            if draft is None
            else score_intake_fields(case.expected, draft)
        )
        per_case.append(
            {
                "case_id": case.case_id,
                "parsed": draft is not None,
                "field_accuracy": round(field_accuracy(matches), 4),
                "fields": matches,
                "latency_ms": round(latency_ms, 2),
                "error": error,
            }
        )
    latencies = [float(entry["latency_ms"]) for entry in per_case]
    accuracies = [float(entry["field_accuracy"]) for entry in per_case]
    return {
        "mean_field_accuracy": round(_mean(accuracies), 4),
        "perfect_cases": sum(1 for value in accuracies if value == 1.0),
        "parse_failures": sum(1 for entry in per_case if not entry["parsed"]),
        "p50_ms": _percentile(latencies, 0.5),
        "p95_ms": _percentile(latencies, 0.95),
        "per_case": per_case,
    }


def run_qa_suite(cases: list[QaCase], service: PolicyQaService) -> dict[str, object]:
    per_case: list[dict[str, object]] = []
    for case in cases:
        started = time.monotonic()
        error: str | None = None
        sections: list[dict[str, object]] = []
        answer: str | None = None
        retrieval_mode = "lexical"
        try:
            result = service.ask(case.question, on_date=case.on_date, role=BENCHMARK_ROLE)
        except ValueBridgeError as exc:
            error = exc.code
        else:
            sections = list(result["sections"])  # type: ignore[arg-type]
            answer = result["answer"]  # type: ignore[assignment]
            retrieval_mode = str(result["retrieval_mode"])
        latency_ms = (time.monotonic() - started) * 1000
        top = sections[0] if sections else None
        per_case.append(
            {
                "case_id": case.case_id,
                "top1_hit": top1_hit(case, sections, answer),
                "groundedness": round(groundedness(case.must_contain, answer), 4),
                "abstained": is_abstention(answer, sections),
                "abstain_expected": case.abstain,
                "retrieval_mode": retrieval_mode,
                "top_section": (
                    None
                    if top is None
                    else {
                        "document_id": str(top["document_id"]),
                        "section_id": str(top["section_id"]),
                    }
                ),
                "latency_ms": round(latency_ms, 2),
                "error": error,
            }
        )
    latencies = [float(entry["latency_ms"]) for entry in per_case]
    return {
        "top1_accuracy": round(_mean([1.0 if entry["top1_hit"] else 0.0 for entry in per_case]), 4),
        "groundedness": round(_mean([float(entry["groundedness"]) for entry in per_case]), 4),
        "abstain_accuracy": round(
            _mean(
                [
                    1.0 if entry["abstained"] == entry["abstain_expected"] else 0.0
                    for entry in per_case
                ]
            ),
            4,
        ),
        "p50_ms": _percentile(latencies, 0.5),
        "p95_ms": _percentile(latencies, 0.95),
        "per_case": per_case,
    }


def build_report(models: list[dict[str, object]]) -> dict[str, object]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": models,
    }


def format_comparison_table(report: dict[str, object]) -> str:
    models = list(report["models"])  # type: ignore[arg-type]
    names = [str(model["model"]) for model in models]
    rows: list[tuple[str, list[str]]] = []
    for suite, metric, template in _TABLE_ROWS:
        if not any(suite in model for model in models):
            continue
        values = [
            template.format(model[suite][metric]) if suite in model else "-"  # type: ignore[index]
            for model in models
        ]
        rows.append((f"{suite}.{metric}", values))

    label_width = max([len("metric"), *(len(label) for label, _ in rows)])
    widths = [
        max([len(name), *(len(values[index]) for _, values in rows)])
        for index, name in enumerate(names)
    ]

    def line(label: str, values: list[str]) -> str:
        cells = [value.rjust(width) for value, width in zip(values, widths, strict=True)]
        return "  ".join([label.ljust(label_width), *cells])

    return "\n".join(
        [
            line("metric", names),
            line("-" * label_width, ["-" * width for width in widths]),
            *(line(label, values) for label, values in rows),
        ]
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 2)
