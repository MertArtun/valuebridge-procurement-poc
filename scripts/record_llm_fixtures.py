"""Re-record tests/fixtures/llm_transcripts.json against the live provider.

Requires VALUEBRIDGE_LLM_API_KEY and network access, so it is a local
maintenance tool only: CI stays keyless and offline and never runs it.
"""

from __future__ import annotations

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
    load_prompt,
    prompt_key,
)

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "llm_transcripts.json"
NOTE = (
    "Placeholder transcripts kept deterministic for offline tests; "
    "regenerate with scripts/record_llm_fixtures.py."
)

NARRATOR_USER = json.dumps(
    {
        "analysis": {
            "display_variance_percent": "19.24",
            "historical_median_try": "184500",
            "lead_time_variance_days": 6,
            "standard_lead_time_days": 14,
            "variance_percent": "19.2412",
        },
        "citations": [
            {
                "document_id": "PROC-POL-2026",
                "effective_from": "2026-01-01",
                "section_id": "4.2",
                "section_title": "Finans Onayı",
                "status": "CURRENT",
                "title": "EgeMekanik Satın Alma Politikası",
                "version": "2026.1",
            }
        ],
        "decision": {
            "alternative_quote_missing": True,
            "applicable_rule_ids": ["FINANCE_APPROVAL", "ALTERNATIVE_QUOTES"],
            "blocking_reasons": ["200.000 TL üzerindeki talep finans onayı gerektirir."],
            "certificate_status": "VALID",
            "decision_status": "CONDITIONAL_REVIEW",
            "finance_approval_required": True,
            "lead_time_variance_days": 6,
            "warnings": [],
        },
    },
    ensure_ascii=False,
    sort_keys=True,
)

INTAKE_USER = (
    "Atlas Endüstri'den 220.000 TL tutarında yedek parça alacağız, "
    "tek teklif var ve teslim süresi 20 gün. Talep numarası PR-2026-0042, "
    "talep tarihi 18 Ağustos 2026."
)


def canonical_prompts() -> list[tuple[str, str]]:
    """The (system, user) pairs the offline fixture tests replay."""
    return [
        (load_prompt("narrator_system"), NARRATOR_USER),
        (load_prompt("intake_system"), INTAKE_USER),
    ]


def main() -> int:
    api_key = os.getenv("VALUEBRIDGE_LLM_API_KEY")
    if not api_key:
        print(
            "VALUEBRIDGE_LLM_API_KEY is required to record live LLM fixtures.",
            file=sys.stderr,
        )
        return 1
    client = OpenRouterChatClient(
        api_key=api_key,
        model=os.getenv("VALUEBRIDGE_LLM_MODEL", DEFAULT_MODEL),
        base_url=os.getenv("VALUEBRIDGE_LLM_BASE_URL", DEFAULT_BASE_URL),
    )
    transcripts = {"_note": NOTE}
    for system, user in canonical_prompts():
        transcripts[prompt_key(system, user)] = client.complete(system=system, user=user)
    FIXTURE_PATH.write_text(
        json.dumps(transcripts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Recorded {len(transcripts) - 1} transcripts into {FIXTURE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
