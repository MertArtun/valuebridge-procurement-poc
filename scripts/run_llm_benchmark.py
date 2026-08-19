"""Score one or more live models on the intake and policy-answering benchmarks.

Requires VALUEBRIDGE_LLM_API_KEY and network access, so it is a local
measurement tool only: CI stays keyless and offline and never runs it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OpenRouterChatClient,
)
from app.llm_benchmark import (  # noqa: E402
    build_report,
    format_comparison_table,
    load_intake_cases,
    load_qa_cases,
    run_intake_suite,
    run_qa_suite,
)
from app.policy_qa import PolicyQaService, embedding_client_from_env  # noqa: E402
from app.retrieval import PolicyRepository  # noqa: E402

INTAKE_PATH = ROOT / "evals/benchmarks/intake_benchmark.jsonl"
QA_PATH = ROOT / "evals/benchmarks/qa_benchmark.jsonl"
DOCUMENTS_PATH = ROOT / "data/documents.json"
EMBEDDINGS_PATH = ROOT / "data/policy_embeddings.json"
REPORT_PATH = ROOT / "reports/llm_benchmark.json"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Provider model id; repeat to compare models (default: VALUEBRIDGE_LLM_MODEL)",
    )
    parser.add_argument("--suite", choices=("intake", "qa", "all"), default="all")
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.getenv("VALUEBRIDGE_LLM_API_KEY")
    if not api_key:
        print(
            "VALUEBRIDGE_LLM_API_KEY is required to run the LLM quality benchmark; "
            "it calls a live provider and is never part of the keyless suites.",
            file=sys.stderr,
        )
        return 1

    models = args.models or [os.getenv("VALUEBRIDGE_LLM_MODEL", DEFAULT_MODEL)]
    base_url = os.getenv("VALUEBRIDGE_LLM_BASE_URL", DEFAULT_BASE_URL)
    intake_cases = load_intake_cases(INTAKE_PATH) if args.suite in ("intake", "all") else []
    qa_cases = load_qa_cases(QA_PATH) if args.suite in ("qa", "all") else []
    embedding_client = embedding_client_from_env()

    entries: list[dict[str, object]] = []
    for model in models:
        client = OpenRouterChatClient(api_key=api_key, model=model, base_url=base_url)
        entry: dict[str, object] = {"model": model}
        if intake_cases:
            print(
                f"Running intake suite on {model} ({len(intake_cases)} cases)...",
                file=sys.stderr,
            )
            entry["intake"] = run_intake_suite(intake_cases, client)
        if qa_cases:
            print(f"Running QA suite on {model} ({len(qa_cases)} cases)...", file=sys.stderr)
            entry["qa"] = run_qa_suite(
                qa_cases,
                PolicyQaService(
                    PolicyRepository(DOCUMENTS_PATH),
                    chat_client=client,
                    embedding_client=embedding_client,
                    embeddings_path=EMBEDDINGS_PATH,
                ),
            )
        entries.append(entry)

    report = build_report(entries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(format_comparison_table(report))
    print(f"\nReport: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
