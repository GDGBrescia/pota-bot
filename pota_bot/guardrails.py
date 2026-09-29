"""I guardrail di Pota Bot: regole scritte nel codice, che il modello non può aggirare."""
import re

from google.adk.models.llm_response import LlmResponse
from google.genai import types

MAX_PROPOSTE = 3
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
TELEFONO = re.compile(r"\+?\d[\d\s.-]{7,}\d")
FUORI_TEMA = ["calcio", "politica", "oroscopo", "ricetta"]


def contains_personal_data(args: dict) -> bool:
    testo = " ".join(str(v) for v in args.values())
    return bool(EMAIL.search(testo) or TELEFONO.search(testo))


def guardrail(tool, args, tool_context):
    """Gira PRIMA di ogni strumento. Se restituisce un dict, lo strumento NON viene eseguito."""
    if tool.name == "propose_topic":
        if contains_personal_data(args):
            return {"status": "rifiutato", "motivo": "Niente dati personali (email, telefono) nelle proposte."}
        if tool_context.state.get("proposals_count", 0) >= MAX_PROPOSTE:
            return {"status": "rifiutato", "motivo": f"Massimo {MAX_PROPOSTE} proposte per conversazione."}
    return None  # None = via libera, lo strumento gira normalmente


def blocca_fuori_tema(callback_context, llm_request):
    """Gira PRIMA del modello. Se restituisce una risposta, il modello non viene chiamato."""
    ultimo = llm_request.contents[-1] if llm_request.contents else None
    testo = "".join(p.text or "" for p in (ultimo.parts if ultimo else [])).lower()
    if any(parola in testo for parola in FUORI_TEMA):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(
            text="Pota, di questo non parlo! Chiedimi di eventi, AI o della community.")]))
    return None
