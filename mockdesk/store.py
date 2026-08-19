from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from app.errors import IdempotencyConflictError
from app.models import TicketResult


def _canonical_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


class MockDeskStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    payload_hash TEXT,
                    request_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tickets)").fetchall()
            }
            if "payload_hash" not in columns:
                connection.execute("ALTER TABLE tickets ADD COLUMN payload_hash TEXT")

    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult:
        canonical = _canonical_payload(payload)
        incoming_hash = _payload_hash(canonical)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM tickets WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                stored_hash = existing["payload_hash"] or _payload_hash(
                    _canonical_payload(json.loads(existing["payload_json"]))
                )
                if stored_hash != incoming_hash:
                    connection.rollback()
                    raise IdempotencyConflictError(
                        "The idempotency key was already used with a different payload"
                    )
                if existing["payload_hash"] is None:
                    connection.execute(
                        "UPDATE tickets SET payload_hash = ? WHERE idempotency_key = ?",
                        (stored_hash, idempotency_key),
                    )
                connection.commit()
                return TicketResult(
                    ticket_id=existing["ticket_id"],
                    status="ALREADY_PROCESSED",
                    request_id=existing["request_id"],
                    duplicate_created=False,
                )

            sequence = connection.execute(
                """
                SELECT COALESCE(MAX(CAST(SUBSTR(ticket_id, 4) AS INTEGER)), 1000) + 1 AS next_id
                FROM tickets
                WHERE ticket_id GLOB 'MD-[0-9]*'
                """
            ).fetchone()["next_id"]
            ticket_id = f"MD-{int(sequence)}"
            request_id = str(payload["request_id"])
            connection.execute(
                """
                INSERT INTO tickets (
                    ticket_id, idempotency_key, payload_hash, request_id, payload_json, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    idempotency_key,
                    incoming_hash,
                    request_id,
                    canonical,
                    "OPEN",
                ),
            )
            connection.commit()
        return TicketResult(
            ticket_id=ticket_id,
            status="OPEN",
            request_id=request_id,
            duplicate_created=False,
        )

    def ticket_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
