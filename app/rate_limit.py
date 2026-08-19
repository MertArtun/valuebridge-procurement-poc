from __future__ import annotations

import math
import time
from collections.abc import Callable


class TokenBucketLimiter:
    """Per-client token bucket for the public demo deployment.

    Buckets live in this process only: the demo runs as a single container, and
    a restart handing every client a full bucket is an acceptable reset.
    """

    def __init__(
        self,
        *,
        capacity: int,
        refill_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capacity = float(capacity)
        self._refill_per_second = refill_per_minute / 60.0
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    def consume(self, client: str) -> int | None:
        """Return None when the call is allowed, else the Retry-After seconds."""
        now = self._clock()
        tokens, updated_at = self._buckets.get(client, (self._capacity, now))
        tokens = min(self._capacity, tokens + (now - updated_at) * self._refill_per_second)
        if tokens >= 1.0:
            self._buckets[client] = (tokens - 1.0, now)
            return None
        self._buckets[client] = (tokens, now)
        return max(1, math.ceil((1.0 - tokens) / self._refill_per_second))
