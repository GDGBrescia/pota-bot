"""Guardrail sui costi: massimo N messaggi all'ora per persona."""
import time
from collections import deque
from typing import Callable

WINDOW_SECONDS = 3600


class RateLimiter:
    def __init__(self, max_per_hour: int, clock: Callable[[], float] = time.monotonic):
        if max_per_hour < 1:
            raise ValueError("max_per_hour deve essere almeno 1")
        self._max = max_per_hour
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """True se la persona può mandare un altro messaggio adesso (e lo conta)."""
        now = self._clock()
        hits = self._hits.get(key)
        if hits is not None:
            while hits and now - hits[0] >= WINDOW_SECONDS:
                hits.popleft()
            if not hits:
                del self._hits[key]  # niente voci vuote: la memoria non cresce
                hits = None
        if hits is not None and len(hits) >= self._max:
            return False
        if hits is None:
            hits = self._hits[key] = deque()
        hits.append(now)
        return True
