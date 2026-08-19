"""Build data/policy_embeddings.json for the optional hybrid retrieval layer.

Requires VALUEBRIDGE_LLM_API_KEY and network access, so it is a local
maintenance tool only: CI stays keyless and offline, and both the runtime and
the evaluations fall back to lexical retrieval whenever the file is absent.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm import DEFAULT_BASE_URL  # noqa: E402
from app.policy_qa import DEFAULT_EMBEDDINGS_MODEL, OpenRouterEmbeddingClient  # noqa: E402
from app.retrieval import PolicyRepository  # noqa: E402

OUTPUT_PATH = ROOT / "data" / "policy_embeddings.json"
# The index is built from every trusted document, so it can never widen what a
# narrower role is allowed to retrieve at query time.
INDEXING_ROLE = "solution_engineer"


def main() -> int:
    api_key = os.getenv("VALUEBRIDGE_LLM_API_KEY")
    if not api_key:
        print(
            "VALUEBRIDGE_LLM_API_KEY is required to embed policy sections.",
            file=sys.stderr,
        )
        return 1
    model = os.getenv("VALUEBRIDGE_EMBEDDINGS_MODEL", DEFAULT_EMBEDDINGS_MODEL)
    client = OpenRouterEmbeddingClient(
        api_key=api_key,
        model=model,
        base_url=os.getenv("VALUEBRIDGE_LLM_BASE_URL", DEFAULT_BASE_URL),
    )
    repository = PolicyRepository(ROOT / "data" / "documents.json")
    sections = [
        {
            "document_id": document.document_id,
            "section_id": section.section_id,
            "embedding": client.embed(f"{section.title}\n{section.body}"),
        }
        for document in repository.searchable_documents(INDEXING_ROLE)
        if document.status == "CURRENT"
        for section in document.sections
    ]
    OUTPUT_PATH.write_text(
        json.dumps({"model": model, "sections": sections}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Embedded {len(sections)} sections into {OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
