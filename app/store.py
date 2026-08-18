from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.approvals import ApprovalRequiredError
from app.models import ApprovalRecord, AuditEvent
from app.security import authorize


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cases (
                    approval_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    request_id TEXT,
                    approval_id TEXT,
                    trace_id TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )

    def create_approval(self, request_id: str, action_type: str, requested_by: str) -> ApprovalRecord:
        now = _now()
        record = ApprovalRecord(
            approval_id=f"AP-{uuid4().hex[:10].upper()}",
            request_id=request_id,
            action_type=action_type,
            requested_by=requested_by,
            status="PENDING",
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO approvals (
                    approval_id, request_id, action_type, requested_by, status,
                    approved_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.approval_id,
                    record.request_id,
                    record.action_type,
                    record.requested_by,
                    record.status,
                    record.approved_by,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record

    def approve(self, approval_id: str, approved_by: str, approver_role: str) -> ApprovalRecord:
        authorize(approver_role, "approve_finance_action")
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE approvals SET status = ?, approved_by = ?, updated_at = ? WHERE approval_id = ?",
                ("APPROVED", approved_by, now.isoformat(), approval_id),
            )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Approval {approval_id!r} was not found")
        return ApprovalRecord(
            approval_id=row["approval_id"],
            request_id=row["request_id"],
            action_type=row["action_type"],
            requested_by=row["requested_by"],
            status=row["status"],
            approved_by=row["approved_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def require_approved(self, approval_id: str) -> ApprovalRecord:
        record = self.get_approval(approval_id)
        if record.status != "APPROVED":
            raise ApprovalRequiredError(
                f"Approval {approval_id} must be APPROVED before tool execution"
            )
        return record

    def save_case(self, approval_id: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO cases (approval_id, payload_json) VALUES (?, ?)",
                (approval_id, json.dumps(payload, ensure_ascii=False)),
            )

    def load_case(self, approval_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM cases WHERE approval_id = ?", (approval_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Case for approval {approval_id!r} was not found")
        return json.loads(row["payload_json"])

    def add_audit(
        self,
        *,
        event_type: str,
        actor: str,
        trace_id: str,
        request_id: str | None = None,
        approval_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"EV-{uuid4().hex[:12].upper()}",
            timestamp=_now(),
            event_type=event_type,
            actor=actor,
            request_id=request_id,
            approval_id=approval_id,
            trace_id=trace_id,
            details=details or {},
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, timestamp, event_type, actor, request_id,
                    approval_id, trace_id, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp.isoformat(),
                    event.event_type,
                    event.actor,
                    event.request_id,
                    event.approval_id,
                    event.trace_id,
                    json.dumps(event.details, ensure_ascii=False),
                ),
            )
        return event

    def list_audit(self) -> list[AuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY timestamp ASC"
            ).fetchall()
        return [
            AuditEvent(
                event_id=row["event_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                event_type=row["event_type"],
                actor=row["actor"],
                request_id=row["request_id"],
                approval_id=row["approval_id"],
                trace_id=row["trace_id"],
                details=json.loads(row["details_json"]),
            )
            for row in rows
        ]
