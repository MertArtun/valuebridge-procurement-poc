# ValueBridge — Forward-Deployed Procurement AI Case Study

> From process discovery to a measurable, human-approved enterprise workflow.

ValueBridge is a production-minded portfolio PoC that demonstrates how a Solution Engineer can turn an ambiguous operational process into an explainable, controlled and testable AI-assisted workflow.

## Türkçe özet

Kurgusal EgeMekanik A.Ş. için 220.000 TL tutarındaki bir satın alma talebi incelenir. Sistem güncel politikayı seçer, geçmiş kategori medyanını hesaplar, fiyat sapmasını bulur, teklif ve sertifika kontrollerini yapar, finans onayı ister, açık insan onayından sonra MockDesk üzerinde idempotent ticket oluşturur ve bütün adımları audit trail'e kaydeder.

## Why this project exists

The intended role is not limited to building a chatbot. It requires discovery, requirements analysis, PoC delivery, enterprise integrations, deployment troubleshooting, onboarding and measurable outcomes. ValueBridge makes those capabilities inspectable in one bounded workflow.

## Hero result

| Signal | Deterministic result |
|---|---:|
| Request amount | 220,000 TRY |
| Historical median | 184,500 TRY |
| Variance | 19.2% |
| Required quotes | 2 |
| Received quotes | 1 |
| ISO 9001 expiry | 2026-06-30 |
| Request date | 2026-08-18 |
| Decision | `CONDITIONAL_REVIEW` |
| Policy citations | PROC-POL-2026 §4.2, §4.3; SUP-COMP-2026 §3.1 |

## Architecture

```text
Browser
  → FastAPI ValueBridge
      → Policy repository
      → Purchase-history analysis
      → Deterministic policy engine
      → Approval store
      → Audit store
      → MockDesk HTTP API
```

The application does not require an external LLM. Critical decisions never depend on model output.

## Core behavior already implemented

- Current-versus-superseded policy selection
- Section-level policy references
- Separate supplier-compliance policy citation (SUP-COMP-2026 §3.1)
- Exact Decimal-based price calculations
- Deterministic approval, quote and certificate rules
- Explicit human approval before write actions
- Role checks for analysis, approval, execution and audit
- Idempotent MockDesk ticket creation
- SQLite-backed approvals and audit events
- Prompt-injection pattern detection for untrusted supplier content
- FastAPI API and basic interactive web UI
- Automated tests for the end-to-end hero flow

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python scripts/verify.py
```

Run MockDesk:

```bash
uvicorn mockdesk.main:app --port 8001
```

Run ValueBridge in another terminal:

```bash
MOCKDESK_URL=http://127.0.0.1:8001 uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

Docker alternative:

```bash
docker compose up --build
```

## One-command API demo

After both services are running:

```bash
bash scripts/demo.sh
```

## Repository map

```text
app/          ValueBridge API, domain logic, UI and persistence
mockdesk/     Independent mock enterprise ticketing service
data/         Synthetic policies, suppliers and purchase history
tests/        Automated behavioral tests
docs/         PRD, architecture, FDE case, security and delivery plan
evals/        Evaluation cases for the next implementation wave
docs/         Delivery documentation
scripts/      Verification and demo helpers
```

## Measured-results policy

No business-performance percentage is claimed in this starter. Automated tests validate system behavior, not customer ROI. Workflow-impact metrics remain `NOT_MEASURED` until a real or controlled pilot exists.

## SkyStudio status

The workflow blueprint is based on publicly available SkyStudio product and API documentation. It has not been validated inside an authorized SkyStudio workspace and is not presented as a completed integration.

## Independent project notice

This is an independent portfolio project and is not an official SKYMOD product. SKYMOD and SkyStudio trademarks belong to their respective owner. All companies, people and operational data in the demo are synthetic.
