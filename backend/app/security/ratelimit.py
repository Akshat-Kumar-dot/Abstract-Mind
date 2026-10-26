"""In-memory sliding-window rate limits for log-in, sign-up, guest accounts and
extraction. One process keeps one set of counters, which fits a single
instance; behind several instances, move this to a shared store such as Redis.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque

from fastapi import HTTPException

_MAX_KEYS = 50_000


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float) -> float:
        """Record one attempt. Returns 0 if allowed, else seconds until the
        oldest attempt in the window expires."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > _MAX_KEYS:
                self._prune(now, window)
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return window - (now - q[0])
            q.append(now)
            return 0.0

    def _prune(self, now: float, window: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] > window]:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def enforce(key: str, limit: int, window: float, what: str = "attempts") -> None:
    wait = limiter.hit(key, limit, window)
    if wait:
        minutes = max(1, math.ceil(wait / 60))
        raise HTTPException(
            429,
            f"Too many {what}. Try again in {minutes} minute{'s' if minutes > 1 else ''}.",
            headers={"Retry-After": str(math.ceil(wait))},
        )
