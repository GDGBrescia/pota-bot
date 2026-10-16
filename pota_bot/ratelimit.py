"""Guardrail sui costi: massimo N messaggi all'ora per persona."""
import time
from collections import defaultdict, deque
from typing import Callable

WINDOW_SECONDS = 3600


class RateLimiter:
    def __init__(self, max_per_hour: int, clock: Callable[[], float] = time.monotonic):
        self._max = max_per_hour
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """True se la persona può mandare un altro messaggio adesso (e lo conta)."""
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True
