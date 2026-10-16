"""Gli strumenti di Pota Bot: le funzioni che l'agente può decidere di chiamare.

Il modello legge nome, docstring e tipi di ogni funzione per capire quando usarla.
"""
import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from google.adk.tools import ToolContext

from .news import NewsCache
from .storage import Proposal, ProposalStore

DATA_DIR = Path(__file__).parent / "data"
TIMEZONE = ZoneInfo("Europe/Rome")
MAX_NEWS = 15


def _load(name: str):
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


EVENTS = _load("events")
FAQ = _load("faq")
NEWS = _load("news")

# Le 6 categorie del sondaggio Telegram della community.
Category = Literal["eventi_e_opportunita", "modelli_ai", "strumenti_dev",
                   "ai_business", "ecosistema_google", "paper"]


def today() -> date:
    return datetime.now(TIMEZONE).date()


def split_events(events: list[dict], today: date) -> dict:
    """Divide gli eventi in prossimi (da oggi in poi), passati (dal più recente) e da definire."""
    upcoming, past, undated = [], [], []
    for event in events:
        try:
            day = date.fromisoformat(event["data"])
        except ValueError:
            undated.append(event)
            continue
        (upcoming if day >= today else past).append(event)
    return {
        "oggi": today.isoformat(),
        "prossimi": sorted(upcoming, key=lambda e: e["data"]),
        "passati": sorted(past, key=lambda e: e["data"], reverse=True),
        "da_definire": undated,
    }


def get_upcoming_events() -> dict:
    """Restituisce gli eventi di GDG Brescia: la data di oggi, i prossimi eventi, quelli passati e quelli da definire."""
    return split_events(EVENTS, today())


def get_faq(topic: str) -> dict:
    """Cerca nelle domande frequenti della community GDG Brescia.

    Args:
        topic: l'argomento della domanda in poche parole, ad es. "costi" o "proporre un talk".
    """
    topic = topic.lower()  # confronto per "radici" di parola: "cost" trova costo, costi, costa
    trovate = [f for f in FAQ if any(p in topic for p in f["parole_chiave"])]
    if not trovate:
        return {"trovate": [], "argomenti_disponibili": [f["domanda"] for f in FAQ]}
    return {"trovate": [{"domanda": f["domanda"], "risposta": f["risposta"]} for f in trovate]}


_news_cache = NewsCache()


async def get_news(category: Category) -> dict:
    """Restituisce le notizie degli ultimi giorni su AI e Google, da fonti scelte dalla community.

    Scegli tu, tra le notizie, quelle che riguardano la categoria richiesta, e cita sempre il link.

    Args:
        category: la categoria più adatta alla domanda. Le categorie sono quelle
            scelte dalla community nel sondaggio Telegram.
    """
    items = await _news_cache.get()
    if not items:
        return {"category": category, "fonte": "notizie di repertorio (feed non raggiungibili)",
                "news": NEWS[category]}
    return {
        "category": category,
        "fonte": "feed RSS della settimana",
        "news": [
            {"titolo": i.title, "sintesi": i.summary, "fonte": i.source,
             "data": i.published.date().isoformat() if i.published else None, "link": i.link}
            for i in items[:MAX_NEWS]
        ],
    }


def make_propose_topic(store: ProposalStore):
    """Crea lo strumento propose_topic collegato allo store dove salvare le proposte."""

    async def propose_topic(title: str, reason: str, tool_context: ToolContext) -> dict:
        """Registra una proposta di tema per un prossimo evento di GDG Brescia.

        Args:
            title: il tema proposto, in poche parole.
            reason: perché interessa alla community.
        """
        # Prima si salva, poi si aggiorna lo stato: se il salvataggio fallisce
        # la persona non perde una delle sue proposte. In un thread per non bloccare il server.
        await asyncio.to_thread(store.add, Proposal(title=title, reason=reason))
        count = tool_context.state.get("proposals_count", 0) + 1
        tool_context.state["proposals_count"] = count
        return {"status": "salvata", "totale_proposte": count}

    return propose_topic
