"""Il digest settimanale: notizie dai feed RSS scelti da noi, scritte da Gemini, con i link verificati."""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

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


Generate = Callable[[str], Awaitable[str]]

CATEGORIES = [
    "🎟️ Eventi, hackathon e opportunità",
    "🧠 Nuovi modelli AI",
    "🛠️ Strumenti per sviluppatori",
    "💼 AI per il business",
    "🔵 Ecosistema Google",
    "📄 Ricerca e paper",
]
HEADER = "📰 Il digest della settimana di GDG Brescia"
FOOTER = "Pota! Ne parliamo nel gruppo. Fonti scelte dalla community: github.com/GDGBrescia/pota-bot"
LINK_RE = re.compile(r"https?://[^\s)\]>]+")


def build_prompt(items: list[FeedItem]) -> str:
    news = "\n".join(
        f"[{n}] ({i.source}) {i.title} — {i.summary} — {i.link}" for n, i in enumerate(items, start=1)
    )
    return f"""Sei Pota Bot e scrivi il digest settimanale per il gruppo Telegram di GDG Brescia.

Scegli al massimo 6 notizie dall'elenco qui sotto, le più utili per sviluppatori e aziende,
e raggruppale in queste categorie (solo quelle che servono): {", ".join(CATEGORIES)}.

Formato, in testo semplice senza markdown:
{HEADER}

<categoria>
- <la notizia in una frase, in italiano, fatti e perché conta> <link>

{FOOTER}

Regole:
- Ogni riga di notizia inizia con "- " e finisce con il suo link, copiato ESATTAMENTE dall'elenco.
- Usa solo link presenti nell'elenco. Niente hype, niente superlativi.

Notizie:
{news}
"""


def extract_links(text: str) -> list[str]:
    return [link.rstrip(".,;:") for link in LINK_RE.findall(text)]


def validate_digest(text: str, allowed_links: set[str]) -> list[str]:
    """Elenco dei problemi: vuoto se il digest si può pubblicare."""
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("- ")]
    if not lines:
        return ["Nessuna riga di notizia (righe che iniziano con '- ')."]
    problems = []
    for line in lines:
        links = extract_links(line)
        if not links:
            problems.append(f"Notizia senza link: {line}")
        problems += [f"Link non presente nell'elenco: {link}" for link in links if link not in allowed_links]
    return problems


def fallback_digest(items: list[FeedItem], limit: int = 6) -> str:
    """Versione di riserva senza AI: titoli e link, così non si pubblica mai un link inventato."""
    lines = [f"- {i.title} ({i.source}) {i.link}" for i in items[:limit]]
    return "\n".join([HEADER, "", *lines, "", FOOTER])


async def make_digest(items: list[FeedItem], generate: Generate) -> str:
    if not items:
        return ""
    allowed = {i.link for i in items}
    prompt = build_prompt(items)
    text = (await generate(prompt)).strip()
    problems = validate_digest(text, allowed)
    if problems:
        retry = prompt + "\n\nProblemi da correggere nella versione precedente:\n" + "\n".join(problems)
        text = (await generate(retry)).strip()
        problems = validate_digest(text, allowed)
    if problems:
        logger.warning("Digest di Gemini scartato, uso la versione di riserva: %s", problems)
        return fallback_digest(items)
    return text


async def build_weekly_digest(generate: Generate, http: httpx.AsyncClient | None = None,
                              now: datetime | None = None) -> str:
    http = http or httpx.AsyncClient(timeout=30, headers={"User-Agent": "PotaBot/1.0 (+github.com/GDGBrescia/pota-bot)"})
    now = now or datetime.now(timezone.utc)
    feeds = load_feeds()
    results = await asyncio.gather(*(fetch_feed(http, feed) for feed in feeds), return_exceptions=True)
    items = []
    for feed, result in zip(feeds, results):
        if isinstance(result, Exception):
            logger.warning("Feed %s non disponibile: %s", feed["name"], result)
        else:
            items += result
    return await make_digest(select_recent(items, now=now), generate)


async def gemini_generate(prompt: str) -> str:
    """Il vero generatore: Gemini via API key (variabile GOOGLE_API_KEY)."""
    from google import genai

    from .agent import MODEL

    response = await genai.Client().aio.models.generate_content(model=MODEL, contents=prompt)
    return response.text or ""
