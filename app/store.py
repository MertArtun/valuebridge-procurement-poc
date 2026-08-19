from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple
from uuid import uuid4

from app.approvals import ApprovalRequiredError, InvalidApprovalStateError
from app.errors import AuthorizationError
from app.models import ApprovalRecord, AuditEvent
from app.security import authorize

APPROVAL_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


class ApprovalClaim(NamedTuple):
    approval: ApprovalRecord | None
    reused: bool
    superseded: list[ApprovalRecord]


class SQLiteStore:
    def __init__(self, path: Path, now: Callable[[], datetime] = _now) -> None:
        self.path = path
        self._now_fn = now
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
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
                    required_role TEXT NOT NULL DEFAULT 'finance_approver',
                    case_fingerprint TEXT NOT NULL DEFAULT '',
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(approvals)").fetchall()
            }
            if "expires_at" not in columns:
                connection.execute("ALTER TABLE approvals ADD COLUMN expires_at TEXT")
                fallback = (self._now_fn() + APPROVAL_TTL).isoformat()
                connection.execute(
                    "UPDATE approvals SET expires_at = ? WHERE expires_at IS NULL",
                    (fallback,),
                )
            if "required_role" not in columns:
                connection.execute(
                    "ALTER TABLE approvals ADD COLUMN required_role TEXT "
                    "NOT NULL DEFAULT 'finance_approver'"
                )
            if "case_fingerprint" not in columns:
                connection.execute(
                    "ALTER TABLE approvals ADD COLUMN case_fingerprint TEXT "
                    "NOT NULL DEFAULT ''"
                )

    def create_approval(
        self,
        request_id: str,
        action_type: str,
        requested_by: str,
        required_role: str = "finance_approver",
        case_fingerprint: str = "",
    ) -> ApprovalRecord:
        record = self._new_approval(
            request_id=request_id,
            action_type=action_type,
            requested_by=requested_by,
            required_role=required_role,
            case_fingerprint=case_fingerprint,
            now=self._now_fn(),
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_approval(connection, record)
            connection.commit()
        return record

    def reconcile_approval(
        self,
        *,
        request_id: str,
        action_type: str,
        requested_by: str,
        required_role: str,
        case_fingerprint: str,
        approval_required: bool,
    ) -> ApprovalClaim:
        # One write transaction decides the single live approval of a request: an approval
        # covering the same fingerprint is reused, every other live one is superseded, and a
        # missing one is created only while the decision still requires it.
        now = self._now_fn()
        expired: list[ApprovalRecord] = []
        superseded: list[ApprovalRecord] = []
        approval: ApprovalRecord | None = None
        reused = False
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT * FROM approvals
                WHERE request_id = ? AND status IN ('PENDING', 'APPROVED')
                ORDER BY created_at ASC
                """,
                (request_id,),
            ).fetchall()
            live: list[ApprovalRecord] = []
            for row in rows:
                record = self._record_from_row(row)
                if record.status == "PENDING" and now > record.expires_at:
                    expired.append(self._set_status(connection, record, "EXPIRED", now))
                    continue
                live.append(record)
            if approval_required:
                approval = next(
                    (item for item in live if item.case_fingerprint == case_fingerprint),
                    None,
                )
                reused = approval is not None
                if approval is None:
                    approval = self._new_approval(
                        request_id=request_id,
                        action_type=action_type,
                        requested_by=requested_by,
                        required_role=required_role,
                        case_fingerprint=case_fingerprint,
                        now=now,
                    )
                    self._insert_approval(connection, approval)
            for record in live:
                if approval is not None and record.approval_id == approval.approval_id:
                    continue
                superseded.append(self._set_status(connection, record, "SUPERSEDED", now))
            connection.commit()
        for record in expired:
            self._audit_expiry(record)
        return ApprovalClaim(approval=approval, reused=reused, superseded=superseded)

    @staticmethod
    def _new_approval(
        *,
        request_id: str,
        action_type: str,
        requested_by: str,
        required_role: str,
        case_fingerprint: str,
        now: datetime,
    ) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=f"AP-{uuid4().hex[:10].upper()}",
            request_id=request_id,
            action_type=action_type,
            requested_by=requested_by,
            status="PENDING",
            required_role=required_role,
            case_fingerprint=case_fingerprint,
            created_at=now,
            updated_at=now,
            expires_at=now + APPROVAL_TTL,
        )

    @staticmethod
    def _insert_approval(connection: sqlite3.Connection, record: ApprovalRecord) -> None:
        connection.execute(
            """
            INSERT INTO approvals (
                approval_id, request_id, action_type, requested_by, status,
                required_role, case_fingerprint, approved_by,
                created_at, updated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.approval_id,
                record.request_id,
                record.action_type,
                record.requested_by,
                record.status,
                record.required_role,
                record.case_fingerprint,
                record.approved_by,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                record.expires_at.isoformat(),
            ),
        )

    @staticmethod
    def _set_status(
        connection: sqlite3.Connection,
        record: ApprovalRecord,
        status: str,
        now: datetime,
    ) -> ApprovalRecord:
        connection.execute(
            "UPDATE approvals SET status = ?, updated_at = ? WHERE approval_id = ?",
            (status, now.isoformat(), record.approval_id),
        )
        return record.model_copy(update={"status": status, "updated_at": now})

    def approve(self, approval_id: str, approved_by: str, approver_role: str) -> ApprovalRecord:
        authorize(approver_role, "approve_finance_action")
        return self._transition(
            approval_id,
            target_status="APPROVED",
            approved_by=approved_by,
            approver_role=approver_role,
        )

    def reject(self, approval_id: str, approver_role: str) -> ApprovalRecord:
        authorize(approver_role, "approve_finance_action")
        return self._transition(
            approval_id,
            target_status="REJECTED",
            approver_role=approver_role,
        )

    def _transition(
        self,
        approval_id: str,
        *,
        target_status: str,
        approved_by: str | None = None,
        approver_role: str | None = None,
    ) -> ApprovalRecord:
        now = self._now_fn()
        expired_record: ApprovalRecord | None = None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"Approval {approval_id!r} was not found")
            current = self._record_from_row(row)
            if approver_role is not None and approver_role != current.required_role:
                connection.rollback()
                raise AuthorizationError(
                    f"Approval {approval_id} requires role {current.required_role!r}, "
                    f"but {approver_role!r} attempted the decision"
                )
            if current.status != "PENDING":
                connection.rollback()
                raise InvalidApprovalStateError(
                    f"Approval {approval_id} is {current.status} and cannot transition "
                    f"to {target_status}"
                )
            if now > current.expires_at:
                cursor = connection.execute(
                    """
                    UPDATE approvals
                    SET status = 'EXPIRED', updated_at = ?
                    WHERE approval_id = ? AND status = 'PENDING'
                    """,
                    (now.isoformat(), approval_id),
                )
                connection.commit()
                if cursor.rowcount == 1:
                    expired_record = current.model_copy(
                        update={"status": "EXPIRED", "updated_at": now}
                    )
            else:
                cursor = connection.execute(
                    """
                    UPDATE approvals
                    SET status = ?, approved_by = ?, updated_at = ?
                    WHERE approval_id = ? AND status = 'PENDING' AND expires_at >= ?
                    """,
                    (
                        target_status,
                        approved_by,
                        now.isoformat(),
                        approval_id,
                        now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    current = self.get_approval(approval_id)
                    raise InvalidApprovalStateError(
                        f"Approval {approval_id} is {current.status} and cannot transition "
                        f"to {target_status}"
                    )
                connection.commit()

        if expired_record is not None:
            self._audit_expiry(expired_record)
            raise InvalidApprovalStateError(
                f"Approval {approval_id} is EXPIRED and cannot transition to {target_status}"
            )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Approval {approval_id!r} was not found")
        record = self._record_from_row(row)
        if record.status == "PENDING" and self._now_fn() > record.expires_at:
            return self._expire_if_pending(record)
        return record

    def _expire_if_pending(self, record: ApprovalRecord) -> ApprovalRecord:
        now = self._now_fn()
        changed = False
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE approvals
                SET status = 'EXPIRED', updated_at = ?
                WHERE approval_id = ? AND status = 'PENDING' AND expires_at < ?
                """,
                (now.isoformat(), record.approval_id, now.isoformat()),
            )
            changed = cursor.rowcount == 1
            connection.commit()
        if changed:
            record = record.model_copy(update={"status": "EXPIRED", "updated_at": now})
            self._audit_expiry(record)
            return record
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (record.approval_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Approval {record.approval_id!r} was not found")
        return self._record_from_row(row)

    def _audit_expiry(self, record: ApprovalRecord) -> None:
        try:
            trace_id = self.load_case(record.approval_id)["trace_id"]
        except KeyError:
            trace_id = f"expiry-{record.approval_id}"
        self.add_audit(
            event_type="APPROVAL_EXPIRED",
            actor="system",
            request_id=record.request_id,
            approval_id=record.approval_id,
            trace_id=trace_id,
            details={"expired_at": record.expires_at.isoformat()},
        )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row["approval_id"],
            request_id=row["request_id"],
            action_type=row["action_type"],
            requested_by=row["requested_by"],
            status=row["status"],
            required_role=row["required_role"],
            case_fingerprint=row["case_fingerprint"],
            approved_by=row["approved_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
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
            timestamp=self._now_fn(),
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
