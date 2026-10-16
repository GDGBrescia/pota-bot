"""Il digest settimanale: notizie dai feed RSS scelti da noi, scritte da Gemini, con i link verificati."""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx

logger = logging.getLogger(__name__)

FEEDS_PATH = Path(__file__).parent / "data" / "feeds.json"
MAX_ITEMS_IN_PROMPT = 40


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    source: str
    published: datetime | None
    summary: str


def load_feeds(path: Path = FEEDS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


async def fetch_feed(http: httpx.AsyncClient, feed: dict) -> list[FeedItem]:
    response = await http.get(feed["url"], follow_redirects=True)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    items = []
    for entry in parsed.entries:
        when = entry.get("published_parsed") or entry.get("updated_parsed")
        items.append(FeedItem(
            title=_clean(entry.get("title", "")),
            link=entry.get("link", ""),
            source=feed["name"],
            published=datetime(*when[:6], tzinfo=timezone.utc) if when else None,
            summary=_clean(entry.get("summary", ""))[:300],
        ))
    return [i for i in items if i.title and i.link.startswith("http")]


def select_recent(items: list[FeedItem], now: datetime, days: int = 7, undated_per_source: int = 3) -> list[FeedItem]:
    """Le notizie degli ultimi `days` giorni, più recenti prima, e qualche notizia senza data per fonte."""
    since = now - timedelta(days=days)
    dated = sorted((i for i in items if i.published and i.published >= since), key=lambda i: i.published, reverse=True)
    undated, per_source = [], {}
    for i in items:
        if i.published is None and per_source.get(i.source, 0) < undated_per_source:
            undated.append(i)
            per_source[i.source] = per_source.get(i.source, 0) + 1
    return (dated + undated)[:MAX_ITEMS_IN_PROMPT]
