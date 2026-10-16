from datetime import date, datetime, timezone

from pota_bot import tools
from pota_bot.digest import FeedItem
from pota_bot.news import NewsCache

EVENTS = [
    {"data": "2026-07-16", "titolo": "Luglio"},
    {"data": "2026-10-01", "titolo": "Ottobre"},
    {"data": "2026-11-12", "titolo": "Novembre"},
    {"data": "da definire", "titolo": "Natale"},
]


def test_split_events_uses_today():
    result = tools.split_events(EVENTS, today=date(2026, 10, 20))
    assert result["oggi"] == "2026-10-20"
    assert [e["titolo"] for e in result["prossimi"]] == ["Novembre"]
    assert [e["titolo"] for e in result["passati"]] == ["Ottobre", "Luglio"]
    assert [e["titolo"] for e in result["da_definire"]] == ["Natale"]


def test_event_today_counts_as_upcoming():
    result = tools.split_events(EVENTS, today=date(2026, 11, 12))
    assert [e["titolo"] for e in result["prossimi"]] == ["Novembre"]


def news_item(title):
    return FeedItem(title=title, link=f"https://ex.com/{title}", source="Fonte",
                    published=datetime(2026, 10, 19, tzinfo=timezone.utc), summary="sintesi")


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


async def test_news_cache_fetches_once_per_hour():
    calls = []

    async def fetch():
        calls.append(1)
        return [news_item("a")]

    clock = FakeClock()
    cache = NewsCache(fetch=fetch, clock=clock)
    await cache.get()
    clock.now = 3599
    await cache.get()
    assert len(calls) == 1
    clock.now = 3600
    await cache.get()
    assert len(calls) == 2


async def test_news_cache_keeps_old_news_if_feeds_fail():
    responses = [[news_item("a")], RuntimeError("rete giù")]

    async def fetch():
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    clock = FakeClock()
    cache = NewsCache(fetch=fetch, clock=clock)
    assert [i.title for i in await cache.get()] == ["a"]
    clock.now = 4000
    assert [i.title for i in await cache.get()] == ["a"]


async def test_get_news_returns_fresh_feed_items(monkeypatch):
    async def fetch():
        return [news_item("fresca")]

    monkeypatch.setattr(tools, "_news_cache", NewsCache(fetch=fetch))
    result = await tools.get_news("modelli_ai")
    assert result["fonte"] == "feed RSS della settimana"
    assert result["news"][0]["titolo"] == "fresca"
    assert result["news"][0]["link"] == "https://ex.com/fresca"


async def test_get_news_falls_back_to_curated_news(monkeypatch):
    async def fetch():
        return []

    monkeypatch.setattr(tools, "_news_cache", NewsCache(fetch=fetch))
    result = await tools.get_news("modelli_ai")
    assert result["fonte"].startswith("notizie di repertorio")
    assert result["news"] == tools.NEWS["modelli_ai"]
