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

INTAKE_USER = (
    "Atlas Endüstri'den 220.000 TL tutarında yedek parça alacağız, "
    "tek teklif var ve teslim süresi 20 gün. Talep numarası PR-2026-0042, "
    "talep tarihi 18 Ağustos 2026."
)


def _hero_narrator_user() -> str:
    """Build the narrator payload from the real engine so the canonical case
    can never drift from what the demo actually shows."""
    import tempfile

    from app.mockdesk_client import InProcessMockDeskGateway
    from app.models import PurchaseRequest
    from app.service import ProcurementService
    from app.store import SQLiteStore
    from mockdesk.store import MockDeskStore

    with tempfile.TemporaryDirectory() as tmp:
        service = ProcurementService.from_project_data(
            store=SQLiteStore(Path(tmp) / "valuebridge.db"),
            mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(Path(tmp) / "mockdesk.db")),
            project_root=ROOT,
        )
        response = service.analyze(
            PurchaseRequest(
                request_id="PR-2026-0042",
                request_date="2026-08-18",
                supplier_name="Atlas Endüstri",
                category="SPARE_PARTS",
                amount_try="220000",
                received_quotes=1,
                offered_lead_time_days=20,
            ),
            role="procurement_specialist",
            user="fixture_recorder",
        )
        return service._narrator_user_message(response)


def canonical_prompts() -> list[tuple[str, str]]:
    """The (system, user) pairs the offline fixture tests replay."""
    return [
        (load_prompt("narrator_system"), _hero_narrator_user()),
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
