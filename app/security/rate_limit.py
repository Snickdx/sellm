"""Coarse in-process rate limits for login / chat / uploads."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    def allow(self, bucket: str, key: str, *, limit: int, window_seconds: float) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            cutoff = now - window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


rate_limiter = RateLimiter()
