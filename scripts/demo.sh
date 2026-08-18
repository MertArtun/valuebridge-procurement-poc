#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PAYLOAD="$(cat data/example_request.json)"

printf '\n1) Analyze hero request\n'
ANALYSIS="$(curl -fsS -X POST "$BASE_URL/api/v1/requests/analyze" \
  -H 'Content-Type: application/json' \
  -H 'X-Demo-Role: procurement_specialist' \
  -H 'X-Demo-User: procurement_user' \
  -d "$PAYLOAD")"
printf '%s\n' "$ANALYSIS" | python -m json.tool

APPROVAL_ID="$(printf '%s' "$ANALYSIS" | python -c 'import json,sys; print(json.load(sys.stdin)["approval"]["approval_id"])')"

printf '\n2) Prove execution is blocked before approval\n'
curl -sS -X POST "$BASE_URL/api/v1/tool-actions/$APPROVAL_ID/execute" \
  -H 'X-Demo-Role: procurement_specialist' \
  -H 'X-Demo-User: procurement_user' | python -m json.tool

printf '\n3) Approve as finance user\n'
curl -fsS -X POST "$BASE_URL/api/v1/approvals/$APPROVAL_ID/approve" \
  -H 'X-Demo-Role: finance_approver' \
  -H 'X-Demo-User: finance_user' | python -m json.tool

printf '\n4) Execute approved action\n'
curl -fsS -X POST "$BASE_URL/api/v1/tool-actions/$APPROVAL_ID/execute" \
  -H 'X-Demo-Role: procurement_specialist' \
  -H 'X-Demo-User: procurement_user' | python -m json.tool

printf '\n5) Execute again to prove idempotency\n'
curl -fsS -X POST "$BASE_URL/api/v1/tool-actions/$APPROVAL_ID/execute" \
  -H 'X-Demo-Role: procurement_specialist' \
  -H 'X-Demo-User: procurement_user' | python -m json.tool

printf '\n6) Read audit trail\n'
curl -fsS "$BASE_URL/api/v1/audit/events" \
  -H 'X-Demo-Role: solution_engineer' \
  -H 'X-Demo-User: solution_engineer' | python -m json.tool
