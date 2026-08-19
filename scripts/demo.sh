#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
PAYLOAD="$(cat data/example_request.json)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

printf 'Waiting for %s/health ...\n' "$BASE_URL"
ready=0
for _ in $(seq 1 30); do
  if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo "Service at $BASE_URL did not become ready" >&2
  exit 1
fi

request() {
  local expected="$1"
  local output="$2"
  shift 2
  local status
  status="$(curl -sS -o "$output" -w '%{http_code}' "$@")"
  if [[ "$status" != "$expected" ]]; then
    echo "Expected HTTP $expected, got $status" >&2
    cat "$output" >&2
    exit 1
  fi
}

printf '\n1) Analyze hero request\n'
request 200 "$TMP_DIR/analysis.json" -X POST "$BASE_URL/api/v1/requests/analyze" \
  -H 'Content-Type: application/json' \
  -H 'X-Demo-Role: procurement_specialist' \
  -H 'X-Demo-User: procurement_user' \
  -d "$PAYLOAD"
"$PYTHON_BIN" -m json.tool "$TMP_DIR/analysis.json"

APPROVAL_ID="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1]))["approval"]["approval_id"])' "$TMP_DIR/analysis.json")"
APPROVAL_STATUS="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1]))["approval"]["status"])' "$TMP_DIR/analysis.json")"

if [[ "$APPROVAL_STATUS" == "PENDING" ]]; then
  printf '\n2) Prove execution is blocked before approval\n'
  request 409 "$TMP_DIR/blocked.json" -X POST "$BASE_URL/api/v1/tool-actions/$APPROVAL_ID/execute" \
    -H 'X-Demo-Role: procurement_specialist' \
    -H 'X-Demo-User: procurement_user'
  "$PYTHON_BIN" -m json.tool "$TMP_DIR/blocked.json"
  "$PYTHON_BIN" - "$TMP_DIR/blocked.json" <<'PY'
import json, sys
body = json.load(open(sys.argv[1]))
assert body["error"]["code"] == "APPROVAL_REQUIRED", body
PY

  printf '\n3) Approve as finance user\n'
  request 200 "$TMP_DIR/approved.json" -X POST "$BASE_URL/api/v1/approvals/$APPROVAL_ID/approve" \
    -H 'X-Demo-Role: finance_approver' \
    -H 'X-Demo-User: finance_user'
  "$PYTHON_BIN" -m json.tool "$TMP_DIR/approved.json"
elif [[ "$APPROVAL_STATUS" == "APPROVED" ]]; then
  # A persistent volume can hold the already-granted approval from a previous
  # identical run; execution replay is then the only remaining valid step.
  printf '\n2-3) Approval already APPROVED from a previous run; skipping block and approve steps\n'
else
  echo "Unexpected approval status: $APPROVAL_STATUS" >&2
  exit 1
fi

printf '\n4) Execute approved action\n'
request 200 "$TMP_DIR/first.json" -X POST "$BASE_URL/api/v1/tool-actions/$APPROVAL_ID/execute" \
  -H 'X-Demo-Role: procurement_specialist' \
  -H 'X-Demo-User: procurement_user'
"$PYTHON_BIN" -m json.tool "$TMP_DIR/first.json"

printf '\n5) Execute again to prove idempotency\n'
request 200 "$TMP_DIR/second.json" -X POST "$BASE_URL/api/v1/tool-actions/$APPROVAL_ID/execute" \
  -H 'X-Demo-Role: procurement_specialist' \
  -H 'X-Demo-User: procurement_user'
"$PYTHON_BIN" -m json.tool "$TMP_DIR/second.json"
"$PYTHON_BIN" - "$TMP_DIR/first.json" "$TMP_DIR/second.json" <<'PY'
import json, sys
first = json.load(open(sys.argv[1]))
second = json.load(open(sys.argv[2]))
# A persistent MockDesk volume may already hold this ticket from an
# earlier run; the invariant is one ticket per approval, not freshness.
assert first["status"] in {"OPEN", "ALREADY_PROCESSED"}, first
assert second["status"] == "ALREADY_PROCESSED", second
assert first["ticket_id"] == second["ticket_id"], (first, second)
assert second["duplicate_created"] is False, second
PY

printf '\n6) Read audit trail\n'
request 200 "$TMP_DIR/audit.json" "$BASE_URL/api/v1/audit/events" \
  -H 'X-Demo-Role: solution_engineer' \
  -H 'X-Demo-User: solution_engineer'
"$PYTHON_BIN" -m json.tool "$TMP_DIR/audit.json"
"$PYTHON_BIN" - "$TMP_DIR/audit.json" <<'PY'
import json, sys
items = json.load(open(sys.argv[1]))
events = {item["event_type"] for item in items}
required = {
    "REQUEST_RECEIVED",
    "POLICY_RETRIEVED",
    "POLICY_EVALUATED",
    "APPROVAL_REQUESTED",
    "APPROVAL_GRANTED",
    "TOOL_EXECUTED",
}
assert required <= events, required - events
PY

echo "PASS: end-to-end demo assertions"
