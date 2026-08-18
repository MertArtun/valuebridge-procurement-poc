from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.models import TicketResult


class MockDeskStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    request_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_ticket(self, payload: dict[str, object], idempotency_key: str) -> TicketResult:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM tickets WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                return TicketResult(
                    ticket_id=existing["ticket_id"],
                    status="ALREADY_PROCESSED",
                    request_id=existing["request_id"],
                    duplicate_created=False,
                )

            count = connection.execute("SELECT COUNT(*) AS count FROM tickets").fetchone()["count"]
            ticket_id = f"MD-{1001 + count}"
            request_id = str(payload["request_id"])
            connection.execute(
                """
                INSERT INTO tickets (
                    ticket_id, idempotency_key, request_id, payload_json, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    idempotency_key,
                    request_id,
                    json.dumps(payload, ensure_ascii=False),
                    "OPEN",
                ),
            )
        return TicketResult(
            ticket_id=ticket_id,
            status="OPEN",
            request_id=request_id,
            duplicate_created=False,
        )

    def ticket_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
