from datetime import datetime, timedelta, timezone

import httpx

from pota_bot.digest import FeedItem, fetch_feed, load_feeds, select_recent

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Notizia nuova</title><link>https://ex.com/nuova</link>
<pubDate>Sat, 17 Oct 2026 10:00:00 +0000</pubDate><description>&lt;p&gt;Testo &lt;b&gt;breve&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>Senza data</title><link>https://ex.com/senza-data</link></item>
</channel></rss>"""


def item(title, days_ago=None, source="S"):
    published = None if days_ago is None else NOW - timedelta(days=days_ago)
    return FeedItem(title=title, link=f"https://ex.com/{title}", source=source, published=published, summary="")


def test_feeds_file_is_valid():
    feeds = load_feeds()
    assert feeds and all(f["url"].startswith("https://") and f["name"] for f in feeds)


async def test_fetch_feed_parses_items_and_strips_html():
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=RSS)))
    items = await fetch_feed(http, {"name": "Esempio", "url": "https://ex.com/rss"})
    assert [i.title for i in items] == ["Notizia nuova", "Senza data"]
    assert items[0].summary == "Testo breve"
    assert items[0].published == datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)
    assert items[1].published is None


def test_select_recent_keeps_last_week_newest_first():
    chosen = select_recent([item("vecchia", 10), item("ieri", 1), item("oggi", 0)], now=NOW)
    assert [i.title for i in chosen] == ["oggi", "ieri"]


def test_select_recent_keeps_a_few_undated_per_source():
    undated = [item(f"n{i}", None, source="Dev") for i in range(5)]
    chosen = select_recent(undated, now=NOW, undated_per_source=3)
    assert [i.title for i in chosen] == ["n0", "n1", "n2"]


from pota_bot.digest import build_weekly_digest, fallback_digest, make_digest, validate_digest

GOOD = "Il digest\n\n🧠 Nuovi modelli AI\n- Notizia uno. https://ex.com/uno\n\nPota!"


def test_validate_accepts_known_links():
    assert validate_digest(GOOD, {"https://ex.com/uno"}) == []


def test_validate_rejects_invented_link_and_missing_link():
    text = "- Inventata. https://falso.com/x\n- Senza fonte."
    problems = validate_digest(text, {"https://ex.com/uno"})
    assert len(problems) == 2


def test_validate_requires_at_least_one_news_line():
    assert validate_digest("Niente notizie", set()) != []


async def test_make_digest_returns_valid_text():
    items = [item("uno", 1)]

    async def generate(prompt):
        assert "https://ex.com/uno" in prompt
        return "Digest\n- Uno. https://ex.com/uno"

    assert await make_digest(items, generate) == "Digest\n- Uno. https://ex.com/uno"


async def test_make_digest_retries_then_falls_back_without_ai():
    items = [item("uno", 1)]
    prompts = []

    async def generate(prompt):
        prompts.append(prompt)
        return "- Inventata. https://falso.com/x"

    text = await make_digest(items, generate)
    assert len(prompts) == 2
    assert "Problemi" in prompts[1]
    assert text == fallback_digest(items)
    assert "https://ex.com/uno" in text


async def test_make_digest_with_no_items_is_empty():
    async def generate(prompt):
        raise AssertionError("non deve chiamare il modello")

    assert await make_digest([], generate) == ""


async def test_build_weekly_digest_skips_broken_feeds(monkeypatch):
    def handler(request):
        if "rotto" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, text=RSS)

    monkeypatch.setattr("pota_bot.digest.load_feeds", lambda: [
        {"name": "Buono", "url": "https://ex.com/rss"},
        {"name": "Rotto", "url": "https://rotto.com/rss"},
    ])

    async def generate(prompt):
        return "Digest\n- Nuova. https://ex.com/nuova"

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    text = await build_weekly_digest(generate, http=http, now=NOW)
    assert "https://ex.com/nuova" in text
