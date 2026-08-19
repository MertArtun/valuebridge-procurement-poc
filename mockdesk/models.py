from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TicketResult(BaseModel):
    ticket_id: str
    status: Literal["OPEN", "ALREADY_PROCESSED"]
    request_id: str
    duplicate_created: bool = False
