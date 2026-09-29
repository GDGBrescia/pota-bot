"""Gli strumenti di Pota Bot: le funzioni che l'agente può decidere di chiamare.

Il modello legge nome, docstring e tipi di ogni funzione per capire quando usarla.
"""
import json
from pathlib import Path
from typing import Literal

from google.adk.tools import ToolContext

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str):
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


EVENTS = _load("events")
FAQ = _load("faq")
NEWS = _load("news")

# Le 6 categorie del sondaggio Telegram della community.
Category = Literal["eventi_e_opportunita", "modelli_ai", "strumenti_dev",
                   "ai_business", "ecosistema_google", "paper"]


def get_upcoming_events() -> dict:
    """Restituisce gli eventi di GDG Brescia (passati e futuri) con data, titolo e luogo."""
    return {"events": EVENTS}


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


def get_news(category: Category) -> dict:
    """Restituisce le notizie della settimana su AI e Google per una categoria.

    Args:
        category: la categoria più adatta alla domanda. Le categorie sono quelle
            scelte dalla community nel sondaggio Telegram.
    """
    return {"category": category, "news": NEWS[category]}


def propose_topic(title: str, reason: str, tool_context: ToolContext) -> dict:
    """Registra una proposta di tema per un prossimo evento di GDG Brescia.

    Args:
        title: il tema proposto, in poche parole.
        reason: perché interessa alla community.
    """
    proposals = tool_context.state.get("proposals", [])
    proposals.append({"title": title, "reason": reason})
    tool_context.state["proposals"] = proposals
    tool_context.state["proposals_count"] = len(proposals)
    return {"status": "salvata", "totale_proposte": len(proposals)}
