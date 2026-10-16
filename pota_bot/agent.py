"""Pota Bot: l'agente della community GDG Brescia.

ADK cerca `root_agent` in questo file: `adk web` e `adk run pota_bot` lo trovano da soli.
"""
import os

from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.base_llm import BaseLlm
from google.adk.models.google_llm import Gemini
from google.genai import types

from .guardrails import blocca_fuori_tema, guardrail
from .storage import MemoryProposalStore, ProposalStore
from .tools import get_faq, get_news, get_upcoming_events, make_propose_topic, today

# Il modello si sceglie con la variabile d'ambiente POTA_BOT_MODEL.
MODEL = os.environ.get("POTA_BOT_MODEL", "gemini-3.5-flash-lite")

# Se Gemini è momentaneamente sovraccarico (500/503/504) riproviamo da soli, con attese crescenti.
# Il 429 (quota finita) no: riprovare consumerebbe altra quota.
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=4, initial_delay=1.0, max_delay=8.0, http_status_codes=[500, 503, 504]
)

INSTRUCTION = """
Sei Pota Bot, l'assistente della community GDG Brescia (Google Developer Group).

Tono: diretto, pratico e amichevole, con un pizzico di bresciano ("Pota!"). Risposte brevi.

Regole:
- Per i fatti (date, luoghi, notizie) usa SEMPRE gli strumenti che hai. Non inventare.
- Se non hai l'informazione, dillo chiaramente.
- Rispondi in italiano.
- Parli solo di: community GDG Brescia ed eventi, AI, sviluppo software e tecnologie Google.
  Per qualsiasi altro argomento (ricette, sport, politica, compiti, consigli personali…) declina in una frase
  e riporta la conversazione sui tuoi temi, SENZA dare comunque la risposta, nemmeno in parte.
- Scrivi testo semplice, senza markdown, al massimo 800 caratteri: i messaggi finiscono su Telegram.
"""


def instruction_for_today(context: ReadonlyContext) -> str:
    """Le istruzioni con la data di oggi: il modello da solo non sa che giorno è."""
    return f"{INSTRUCTION}\nOggi è {today():%d/%m/%Y}."


def build_agent(store: ProposalStore, model: str | BaseLlm = MODEL) -> Agent:
    """Costruisce l'agente. Lo store decide dove finiscono le proposte di temi."""
    if isinstance(model, str):
        model = Gemini(model=model, retry_options=RETRY_OPTIONS)
    return Agent(
        name="pota_bot",
        model=model,
        instruction=instruction_for_today,
        tools=[get_upcoming_events, get_faq, get_news, make_propose_topic(store)],
        before_tool_callback=guardrail,
        before_model_callback=blocca_fuori_tema,
    )


# Store in memoria: serve solo a `adk web`/`adk run` in locale; in produzione si costruisce un agente con Firestore.
root_agent = build_agent(MemoryProposalStore())
