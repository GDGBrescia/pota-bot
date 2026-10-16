"""Notizie fresche per la chat: le stesse fonti RSS del digest, tenute in memoria per un'ora.

Così il bot non scarica i feed a ogni domanda, e se i feed non rispondono usa l'ultima copia buona.
"""
import logging
import time
from typing import Awaitable, Callable

from .digest import FeedItem, fetch_recent_items

logger = logging.getLogger(__name__)

CACHE_SECONDS = 3600


class NewsCache:
    def __init__(self, fetch: Callable[[], Awaitable[list[FeedItem]]] = fetch_recent_items,
                 clock: Callable[[], float] = time.monotonic):
        self._fetch = fetch
        self._clock = clock
        self._items: list[FeedItem] = []
        self._fetched_at: float | None = None

    async def get(self) -> list[FeedItem]:
        now = self._clock()
        if self._fetched_at is not None and now - self._fetched_at < CACHE_SECONDS:
            return self._items
        try:
            self._items = await self._fetch()
        except Exception:
            logger.exception("Feed RSS non raggiungibili: uso l'ultima copia")
        self._fetched_at = now
        return self._items
