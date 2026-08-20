# Assumptions, Limitations and Ethics

## Assumptions

- The hero request represents a high-value purchase exception.
- Procurement and finance roles are sufficient for the bounded workflow.
- The synthetic CSV is authoritative for the demonstration.
- MockDesk represents an integration boundary, not a real enterprise system.

## Limitations

- No real customer discovery or live SkyStudio workspace was used.
- Demo headers are not production identity or SSO.
- Manifest-backed retrieval with BM25 and an optional file-based embedding index is not a governed enterprise RAG pipeline.
- Model output is display-only and ungraded; the frozen evaluations assert governance and decisions, not answer wording.
- Pattern detection is not a complete prompt-injection defense.
- SQLite audit storage is not immutable, although approval and idempotency transitions are atomic in the local database.
- No customer adoption, ROI, accuracy or time-saving result is measured.

## Ethical boundary

- The system does not autonomously approve purchases.
- A human owns financial approval.
- Real customer or employee data must not be added to the public repository.
- Supplier content is untrusted.
- Optional model narration must not obscure or modify deterministic decision inputs.

## Trademark boundary

This repository is independent and not endorsed by SKYMOD. SKYMOD and SkyStudio names are used only to explain role alignment and a public-documentation-based workflow blueprint.
