"""Pota Bot: l'agente della community GDG Brescia.

ADK cerca `root_agent` in questo file: `adk web` e `adk run pota_bot` lo trovano da soli.
"""
import os

from google.adk import Agent

from .guardrails import blocca_fuori_tema, guardrail
from .tools import get_faq, get_news, get_upcoming_events, propose_topic

# Il modello si sceglie con la variabile d'ambiente POTA_BOT_MODEL.
MODEL = os.environ.get("POTA_BOT_MODEL", "gemini-3.5-flash-lite")

INSTRUCTION = """
Sei Pota Bot, l'assistente della community GDG Brescia (Google Developer Group).

Tono: diretto, pratico e amichevole, con un pizzico di bresciano ("Pota!"). Risposte brevi.

Regole:
- Per i fatti (date, luoghi, notizie) usa SEMPRE gli strumenti che hai. Non inventare.
- Se non hai l'informazione, dillo chiaramente.
- Rispondi in italiano.
"""

root_agent = Agent(
    name="pota_bot",
    model=MODEL,
    instruction=INSTRUCTION,
    tools=[get_upcoming_events, get_faq, get_news, propose_topic],
    before_tool_callback=guardrail,
    before_model_callback=blocca_fuori_tema,
)
