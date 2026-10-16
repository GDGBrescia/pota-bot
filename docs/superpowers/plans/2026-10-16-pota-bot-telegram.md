# Pota Bot su Telegram + deploy su Google Cloud — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare Pota Bot in un gruppo Telegram (chat + digest settimanale delle news), deployato su Cloud Run, con script e guida per rifare il deploy dal vivo in un webinar.

**Architecture:** Un servizio FastAPI su Cloud Run riceve i messaggi di Telegram via webhook e li passa all'agente ADK (Gemini, API key). Le proposte di temi vanno in Firestore dietro un'interfaccia `ProposalStore`. Cloud Scheduler chiama ogni lunedì un endpoint che legge feed RSS scelti da noi, fa scrivere il digest a Gemini, verifica i link e lo pubblica. Design completo: [`docs/design.md`](../../design.md).

**Tech Stack:** Python 3.12, Google ADK 2.10.0, google-genai, FastAPI, uvicorn, httpx, feedparser, google-cloud-firestore, pytest + pytest-asyncio; Google Cloud: Cloud Run, Cloud Build, Firestore, Secret Manager, Cloud Scheduler.

**Regole per chi esegue:**
- Lavora nella root del repo `pota-bot`. Tutti i comandi partono da lì.
- Commit in italiano, come il resto del repo, e terminano con la riga `Co-Authored-By` indicata dalla sessione.
- **Non usare mai** il progetto Google Cloud configurato di default in gcloud (è un progetto di lavoro). Ogni comando gcloud porta `--project="$PROJECT_ID"` (Task 12).
- Il notebook `workshop.ipynb` **non va toccato**: non importa il pacchetto e installa solo `requirements.txt`, che resta com'è.

---

## Mappa dei file

| File | Stato | Responsabilità |
|---|---|---|
| `requirements-server.txt` | nuovo | Dipendenze del servizio (include `requirements.txt`) |
| `requirements-dev.txt` | nuovo | Dipendenze per i test |
| `pytest.ini` | nuovo | Configurazione test (asyncio automatico) |
| `tests/conftest.py` | nuovo | `ScriptedLlm`: modello finto per i test dell'agente |
| `pota_bot/ratelimit.py` | nuovo | `RateLimiter`: N messaggi/ora per persona |
| `pota_bot/storage.py` | nuovo | `Proposal`, `ProposalStore`, `MemoryProposalStore`, `FirestoreProposalStore` |
| `pota_bot/tools.py` | modificato | `propose_topic` → `make_propose_topic(store)` |
| `pota_bot/agent.py` | modificato | `build_agent(store, model)`; istruzioni adatte a Telegram |
| `pota_bot/chat.py` | nuovo | `AgentChat`: domanda → risposta finale dell'agente, con sessione |
| `pota_bot/telegram.py` | nuovo | `TelegramClient`: chiamate HTTP alla Bot API |
| `pota_bot/bot.py` | nuovo | `PotaBot`: decide se rispondere, comandi, limiti, errori |
| `pota_bot/data/feeds.json` | nuovo | Fonti RSS del digest |
| `pota_bot/digest.py` | nuovo | Feed → notizie recenti → Gemini → verifica link → testo |
| `pota_bot/config.py` | nuovo | `Settings` dalle variabili d'ambiente |
| `server/__init__.py`, `server/main.py` | nuovi | `create_app(...)`: endpoint FastAPI (testabile) |
| `server/production.py` | nuovo | Collega i pezzi veri: `app` per uvicorn |
| `scripts/run_polling.py` | nuovo | Prova in locale senza cloud (polling) + digest su richiesta |
| `Dockerfile`, `.dockerignore` | nuovi | Immagine per Cloud Run |
| `deploy/config.env.example`, `deploy/deploy.sh`, `deploy/teardown.sh` | nuovi | Deploy e smontaggio con un comando |
| `docs/DEPLOY.md` | nuovo | Guida passo-passo per il webinar |
| `tests/test_*.py` | nuovi | Un file per modulo |

---

### Task 0: Ambiente di sviluppo e test

**Files:**
- Create: `requirements-server.txt`, `requirements-dev.txt`, `pytest.ini`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`

- [ ] **Step 1: Dipendenze**

`requirements-server.txt`:
```
-r requirements.txt
fastapi==0.141.1
uvicorn==0.54.0
httpx==0.28.1
feedparser==6.0.14
google-cloud-firestore==2.34.1
```

`requirements-dev.txt`:
```
-r requirements-server.txt
pytest==9.1.1
pytest-asyncio==1.4.0
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
asyncio_mode = auto
filterwarnings =
    ignore::UserWarning
    ignore::DeprecationWarning
```

- [ ] **Step 2: Ambiente virtuale**

Run:
```bash
python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt
```
Expected: nessun errore.

- [ ] **Step 3: Modello finto per i test** (`tests/__init__.py` vuoto, `tests/conftest.py`):

```python
"""Strumenti condivisi dai test: un modello finto che segue un copione."""
from typing import AsyncGenerator

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field


class ScriptedLlm(BaseLlm):
    """Al posto di Gemini: restituisce, in ordine, le risposte del copione.

    Ogni voce è ("call", (nome_tool, argomenti)) oppure ("text", "testo").
    """

    model: str = "fake-model"
    script: list = Field(default_factory=list)
    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        kind, payload = self.script.pop(0)
        if kind == "call":
            name, args = payload
            part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        else:
            part = types.Part(text=payload)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
```

`tests/test_smoke.py`:
```python
from pota_bot.agent import root_agent


def test_root_agent_loads():
    assert root_agent.name == "pota_bot"
```

- [ ] **Step 4: I test girano**

Run: `.venv/bin/pytest -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add requirements-server.txt requirements-dev.txt pytest.ini tests/
git commit -m "Test: ambiente pytest e modello finto per l'agente"
```

---

### Task 1: Limite di messaggi per persona

**Files:**
- Create: `pota_bot/ratelimit.py`
- Test: `tests/test_ratelimit.py`

- [ ] **Step 1: Test che fallisce**

```python
from pota_bot.ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_allows_up_to_limit_then_blocks():
    clock = FakeClock()
    limiter = RateLimiter(max_per_hour=2, clock=clock)
    assert limiter.allow("anna")
    assert limiter.allow("anna")
    assert not limiter.allow("anna")


def test_limit_is_per_person():
    limiter = RateLimiter(max_per_hour=1, clock=FakeClock())
    assert limiter.allow("anna")
    assert limiter.allow("bruno")


def test_window_slides_after_one_hour():
    clock = FakeClock()
    limiter = RateLimiter(max_per_hour=1, clock=clock)
    assert limiter.allow("anna")
    clock.now = 3599
    assert not limiter.allow("anna")
    clock.now = 3600
    assert limiter.allow("anna")
```

- [ ] **Step 2: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_ratelimit.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pota_bot.ratelimit'`

- [ ] **Step 3: Implementazione**

`pota_bot/ratelimit.py`:
```python
"""Guardrail sui costi: massimo N messaggi all'ora per persona."""
import time
from collections import defaultdict, deque
from typing import Callable

WINDOW_SECONDS = 3600


class RateLimiter:
    def __init__(self, max_per_hour: int, clock: Callable[[], float] = time.monotonic):
        self._max = max_per_hour
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """True se la persona può mandare un altro messaggio adesso (e lo conta)."""
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True
```

- [ ] **Step 4: Verifica che passi**

Run: `.venv/bin/pytest tests/test_ratelimit.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add pota_bot/ratelimit.py tests/test_ratelimit.py
git commit -m "Guardrail: limite di messaggi all'ora per persona"
```

---

### Task 2: Dove si salvano le proposte

**Files:**
- Create: `pota_bot/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Test che fallisce**

```python
from pota_bot.storage import FirestoreProposalStore, MemoryProposalStore, Proposal


def test_memory_store_keeps_proposals():
    store = MemoryProposalStore()
    store.add(Proposal(title="RAG in azienda", reason="interessa a molti"))
    assert [p.title for p in store.items] == ["RAG in azienda"]


class FakeCollection:
    def __init__(self):
        self.added = []

    def add(self, data):
        self.added.append(data)


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


def test_firestore_store_writes_title_reason_and_date_only():
    client = FakeFirestore()
    FirestoreProposalStore(client=client).add(Proposal(title="Agenti", reason="perché sì"))
    [doc] = client.collections["proposals"].added
    assert set(doc) == {"title", "reason", "created_at"}
    assert doc["title"] == "Agenti"
```

- [ ] **Step 2: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_storage.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pota_bot.storage'`

- [ ] **Step 3: Implementazione**

`pota_bot/storage.py`:
```python
"""Dove finiscono le proposte di temi: in memoria (locale e test) o in Firestore (produzione).

Di chi propone non salviamo né nome né id: solo tema, motivo e data.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class Proposal:
    title: str
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProposalStore(Protocol):
    def add(self, proposal: Proposal) -> None: ...


class MemoryProposalStore:
    def __init__(self):
        self.items: list[Proposal] = []

    def add(self, proposal: Proposal) -> None:
        self.items.append(proposal)


class FirestoreProposalStore:
    COLLECTION = "proposals"

    def __init__(self, client=None):
        if client is None:
            from google.cloud import firestore
            client = firestore.Client()
        self._collection = client.collection(self.COLLECTION)

    def add(self, proposal: Proposal) -> None:
        self._collection.add({
            "title": proposal.title,
            "reason": proposal.reason,
            "created_at": proposal.created_at,
        })
```

- [ ] **Step 4: Verifica che passi**

Run: `.venv/bin/pytest tests/test_storage.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add pota_bot/storage.py tests/test_storage.py
git commit -m "Proposte: interfaccia ProposalStore, versione in memoria e Firestore"
```

---

### Task 3: `propose_topic` usa lo store, agente costruito da una funzione

**Files:**
- Modify: `pota_bot/tools.py` (sostituire la funzione `propose_topic`)
- Modify: `pota_bot/agent.py` (tutto il file)
- Test: `tests/test_agent.py`

- [ ] **Step 1: Test che fallisce**

```python
from google.adk.runners import InMemoryRunner

from pota_bot.agent import build_agent
from pota_bot.storage import MemoryProposalStore
from tests.conftest import ScriptedLlm


async def run_once(agent, text):
    runner = InMemoryRunner(agent=agent, app_name="pota_bot")
    return await runner.run_debug(text, quiet=True)


async def test_proposal_is_saved_in_store():
    store = MemoryProposalStore()
    llm = ScriptedLlm(script=[
        ("call", ("propose_topic", {"title": "RAG", "reason": "utile in azienda"})),
        ("text", "Proposta salvata!"),
    ])
    await run_once(build_agent(store, model=llm), "Propongo RAG")
    assert [p.title for p in store.items] == ["RAG"]


async def test_guardrail_blocks_personal_data_and_nothing_is_saved():
    store = MemoryProposalStore()
    llm = ScriptedLlm(script=[
        ("call", ("propose_topic", {"title": "RAG", "reason": "scrivimi a a@b.it"})),
        ("text", "Non posso salvarla."),
    ])
    await run_once(build_agent(store, model=llm), "Propongo RAG, scrivimi a a@b.it")
    assert store.items == []
```

- [ ] **Step 2: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_agent.py -q`
Expected: FAIL, `ImportError: cannot import name 'build_agent'`

- [ ] **Step 3: `pota_bot/tools.py`** — sostituire la funzione `propose_topic` (dall'inizio di `def propose_topic` alla fine del file) con:

```python
def make_propose_topic(store: ProposalStore):
    """Crea lo strumento propose_topic collegato allo store dove salvare le proposte."""

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
        store.add(Proposal(title=title, reason=reason))
        return {"status": "salvata", "totale_proposte": len(proposals)}

    return propose_topic
```

e aggiungere in cima, sotto gli import esistenti:
```python
from .storage import Proposal, ProposalStore
```

- [ ] **Step 4: `pota_bot/agent.py`** — sostituire tutto il contenuto con:

```python
"""Pota Bot: l'agente della community GDG Brescia.

ADK cerca `root_agent` in questo file: `adk web` e `adk run pota_bot` lo trovano da soli.
"""
import os

from google.adk import Agent

from .guardrails import blocca_fuori_tema, guardrail
from .storage import MemoryProposalStore, ProposalStore
from .tools import get_faq, get_news, get_upcoming_events, make_propose_topic

# Il modello si sceglie con la variabile d'ambiente POTA_BOT_MODEL.
MODEL = os.environ.get("POTA_BOT_MODEL", "gemini-3.5-flash-lite")

INSTRUCTION = """
Sei Pota Bot, l'assistente della community GDG Brescia (Google Developer Group).

Tono: diretto, pratico e amichevole, con un pizzico di bresciano ("Pota!"). Risposte brevi.

Regole:
- Per i fatti (date, luoghi, notizie) usa SEMPRE gli strumenti che hai. Non inventare.
- Se non hai l'informazione, dillo chiaramente.
- Rispondi in italiano.
- Scrivi testo semplice, senza markdown, al massimo 800 caratteri: i messaggi finiscono su Telegram.
"""


def build_agent(store: ProposalStore, model=MODEL) -> Agent:
    """Costruisce l'agente. Lo store decide dove finiscono le proposte di temi."""
    return Agent(
        name="pota_bot",
        model=model,
        instruction=INSTRUCTION,
        tools=[get_upcoming_events, get_faq, get_news, make_propose_topic(store)],
        before_tool_callback=guardrail,
        before_model_callback=blocca_fuori_tema,
    )


root_agent = build_agent(MemoryProposalStore())
```

- [ ] **Step 5: Verifica che passi (anche i test precedenti)**

Run: `.venv/bin/pytest -q`
Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add pota_bot/tools.py pota_bot/agent.py tests/test_agent.py
git commit -m "Agente: build_agent(store), proposte salvate nello store, istruzioni per Telegram"
```

---

### Task 4: `AgentChat`, da domanda a risposta

**Files:**
- Create: `pota_bot/chat.py`
- Test: `tests/test_chat.py`

- [ ] **Step 1: Test che fallisce**

```python
from pota_bot.agent import build_agent
from pota_bot.chat import AgentChat
from pota_bot.storage import MemoryProposalStore
from tests.conftest import ScriptedLlm


async def test_ask_returns_final_text_after_tool_call():
    llm = ScriptedLlm(script=[
        ("call", ("get_upcoming_events", {})),
        ("text", "Il prossimo evento è il 12 novembre."),
    ])
    chat = AgentChat(build_agent(MemoryProposalStore(), model=llm))
    reply = await chat.ask(user_id="1", session_id="chat:1", text="Prossimo evento?")
    assert reply == "Il prossimo evento è il 12 novembre."


async def test_same_session_is_reused():
    llm = ScriptedLlm(script=[("text", "Ciao!"), ("text", "Ancora ciao!")])
    chat = AgentChat(build_agent(MemoryProposalStore(), model=llm))
    await chat.ask("1", "chat:1", "ciao")
    assert await chat.ask("1", "chat:1", "ciao di nuovo") == "Ancora ciao!"
```

- [ ] **Step 2: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_chat.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pota_bot.chat'`

- [ ] **Step 3: Implementazione**

`pota_bot/chat.py`:
```python
"""Fa una domanda all'agente e restituisce la risposta finale, tenendo una sessione per conversazione."""
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types


class AgentChat:
    def __init__(self, agent: Agent, app_name: str = "pota_bot"):
        self._runner = InMemoryRunner(agent=agent, app_name=app_name)

    async def ask(self, user_id: str, session_id: str, text: str) -> str:
        sessions = self._runner.session_service
        app = self._runner.app_name
        if await sessions.get_session(app_name=app, user_id=user_id, session_id=session_id) is None:
            await sessions.create_session(app_name=app, user_id=user_id, session_id=session_id)
        message = types.Content(role="user", parts=[types.Part(text=text)])
        reply = ""
        async for event in self._runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                reply = "".join(part.text or "" for part in event.content.parts)
        return reply.strip()
```

- [ ] **Step 4: Verifica che passi**

Run: `.venv/bin/pytest tests/test_chat.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add pota_bot/chat.py tests/test_chat.py
git commit -m "AgentChat: domanda all'agente con sessione per conversazione"
```

---

### Task 5: Client della Bot API di Telegram

**Files:**
- Create: `pota_bot/telegram.py`
- Test: `tests/test_telegram.py`

- [ ] **Step 1: Test che fallisce**

```python
import json

import httpx
import pytest

from pota_bot.telegram import TelegramClient, TelegramError


def client_with(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TelegramClient("TOKEN", http=http)


async def test_send_message_posts_expected_payload():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

    result = await client_with(handler).send_message(42, "ciao", reply_to_message_id=7)
    assert seen["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert seen["body"]["chat_id"] == 42
    assert seen["body"]["text"] == "ciao"
    assert seen["body"]["reply_parameters"] == {"message_id": 7}
    assert seen["body"]["link_preview_options"] == {"is_disabled": True}
    assert result == {"message_id": 5}


async def test_long_text_is_cut_to_telegram_limit():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    await client_with(handler).send_message(1, "x" * 5000)
    assert len(seen["body"]["text"]) == 4096


async def test_telegram_error_is_raised_with_description():
    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(TelegramError, match="chat not found"):
        await client_with(handler).send_message(1, "ciao")
```

- [ ] **Step 2: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_telegram.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pota_bot.telegram'`

- [ ] **Step 3: Implementazione**

`pota_bot/telegram.py`:
```python
"""Le poche chiamate alla Bot API di Telegram che ci servono, con httpx."""
import httpx

API_URL = "https://api.telegram.org"
MAX_TEXT = 4096


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, http: httpx.AsyncClient | None = None):
        self._base = f"{API_URL}/bot{token}"
        self._http = http or httpx.AsyncClient(timeout=45)

    async def _call(self, method: str, **payload):
        response = await self._http.post(f"{self._base}/{method}", json=payload)
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", f"errore Telegram {response.status_code}"))
        return data["result"]

    async def send_message(self, chat_id, text: str, reply_to_message_id: int | None = None):
        payload = {"chat_id": chat_id, "text": text[:MAX_TEXT], "link_preview_options": {"is_disabled": True}}
        if reply_to_message_id is not None:
            payload["reply_parameters"] = {"message_id": reply_to_message_id}
        return await self._call("sendMessage", **payload)

    async def set_webhook(self, url: str, secret_token: str):
        return await self._call("setWebhook", url=url, secret_token=secret_token, allowed_updates=["message"])

    async def delete_webhook(self):
        return await self._call("deleteWebhook")

    async def get_updates(self, offset: int, timeout: int = 30):
        return await self._call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"])
```

- [ ] **Step 4: Verifica che passi**

Run: `.venv/bin/pytest tests/test_telegram.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add pota_bot/telegram.py tests/test_telegram.py
git commit -m "Telegram: client minimo della Bot API con httpx"
```

---

### Task 6: `PotaBot`, quando rispondere e cosa

**Files:**
- Create: `pota_bot/bot.py`
- Test: `tests/test_bot.py`

- [ ] **Step 1: Test che fallisce**

```python
import pytest

from pota_bot.bot import ERROR_TEXT, PRIVACY_TEXT, RATE_LIMIT_TEXT, PotaBot, clean_text, is_addressed_to_bot
from pota_bot.ratelimit import RateLimiter

BOT = "pota_test_bot"


def message(text, chat_type="group", reply_to_username=None, user_id=10):
    msg = {"message_id": 99, "text": text, "chat": {"id": -100, "type": chat_type}, "from": {"id": user_id}}
    if reply_to_username:
        msg["reply_to_message"] = {"from": {"username": reply_to_username, "is_bot": True}}
    return {"update_id": 1, "message": msg}


class FakeTelegram:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append((chat_id, text, reply_to_message_id))


class FakeAsk:
    def __init__(self, reply="risposta", error=None):
        self.questions = []
        self.reply, self.error = reply, error

    async def __call__(self, user_id, session_id, text):
        self.questions.append((user_id, session_id, text))
        if self.error:
            raise self.error
        return self.reply


def make_bot(ask=None, limit=20):
    telegram = FakeTelegram()
    bot = PotaBot(telegram=telegram, ask=ask or FakeAsk(), bot_username=BOT, limiter=RateLimiter(limit))
    return bot, telegram


@pytest.mark.parametrize("msg,expected", [
    (message("ciao", chat_type="private")["message"], True),
    (message("ciao a tutti")["message"], False),
    (message("@Pota_Test_Bot quando è il prossimo evento?")["message"], True),
    (message("e quindi?", reply_to_username=BOT)["message"], True),
    (message("e quindi?", reply_to_username="altro_bot")["message"], False),
])
def test_is_addressed_to_bot(msg, expected):
    assert is_addressed_to_bot(msg, BOT) is expected


def test_clean_text_removes_mention():
    assert clean_text("@pota_test_bot  quando è il prossimo evento?", BOT) == "quando è il prossimo evento?"


async def test_group_message_without_mention_is_ignored():
    bot, telegram = make_bot()
    await bot.handle_update(message("ciao a tutti"))
    assert telegram.sent == []


async def test_mention_gets_answer_as_reply():
    ask = FakeAsk(reply="Il 12 novembre!")
    bot, telegram = make_bot(ask)
    await bot.handle_update(message(f"@{BOT} prossimo evento?"))
    assert ask.questions == [("10", "-100:10", "prossimo evento?")]
    assert telegram.sent == [(-100, "Il 12 novembre!", 99)]


async def test_privacy_command_works_with_bot_suffix():
    bot, telegram = make_bot()
    await bot.handle_update(message(f"/privacy@{BOT}"))
    assert telegram.sent[0][1] == PRIVACY_TEXT


async def test_unknown_command_is_ignored():
    bot, telegram = make_bot()
    await bot.handle_update(message("/sconosciuto"))
    assert telegram.sent == []


async def test_rate_limit_stops_the_agent():
    ask = FakeAsk()
    bot, telegram = make_bot(ask, limit=1)
    await bot.handle_update(message("ciao", chat_type="private"))
    await bot.handle_update(message("ancora", chat_type="private"))
    assert len(ask.questions) == 1
    assert telegram.sent[-1][1] == RATE_LIMIT_TEXT


async def test_agent_error_becomes_friendly_message():
    bot, telegram = make_bot(FakeAsk(error=RuntimeError("quota")))
    await bot.handle_update(message("ciao", chat_type="private"))
    assert telegram.sent[-1][1] == ERROR_TEXT


async def test_updates_without_text_are_ignored():
    bot, telegram = make_bot()
    await bot.handle_update({"update_id": 1, "message": {"message_id": 1, "chat": {"id": 1, "type": "private"}}})
    await bot.handle_update({"update_id": 2, "edited_message": {}})
    assert telegram.sent == []
```

- [ ] **Step 2: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_bot.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pota_bot.bot'`

- [ ] **Step 3: Implementazione**

`pota_bot/bot.py`:
```python
"""Il bot Telegram: decide se un messaggio è per noi, gestisce comandi e limiti, chiede all'agente."""
import logging
import re
from typing import Awaitable, Callable

from .ratelimit import RateLimiter

logger = logging.getLogger(__name__)

Ask = Callable[[str, str, str], Awaitable[str]]

HELP_TEXT = (
    "Pota! Sono Pota Bot, il bot di GDG Brescia.\n"
    "Nei gruppi menzionami o rispondi a un mio messaggio: chiedimi degli eventi, delle FAQ, "
    "delle novità su AI e Google, o proponi un tema per i prossimi eventi.\n"
    "/privacy per sapere come uso i messaggi."
)
PRIVACY_TEXT = (
    "I messaggi che mi scrivi vengono elaborati da Gemini (Google) per risponderti. "
    "Non scrivermi dati personali come email, telefono o indirizzi. "
    "Le proposte di temi vengono salvate senza il tuo nome. "
    "Il mio codice è aperto: github.com/GDGBrescia/pota-bot"
)
RATE_LIMIT_TEXT = "Pota, per quest'ora hai già fatto tante domande! Riprova più tardi."
ERROR_TEXT = "Pota, qualcosa è andato storto. Riprova tra un minuto."
EMPTY_TEXT = "Dimmi pure! Chiedimi degli eventi, delle FAQ o delle novità su AI e Google."

COMMANDS = {"/start": HELP_TEXT, "/help": HELP_TEXT, "/privacy": PRIVACY_TEXT}


def command_of(text: str) -> str | None:
    """"/privacy@pota_bot ciao" → "/privacy"; testo normale → None."""
    if not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0].lower()


def is_addressed_to_bot(message: dict, bot_username: str) -> bool:
    if message.get("chat", {}).get("type") == "private":
        return True
    replied_to = (message.get("reply_to_message") or {}).get("from") or {}
    if replied_to.get("username", "").lower() == bot_username.lower():
        return True
    return f"@{bot_username.lower()}" in (message.get("text") or "").lower()


def clean_text(text: str, bot_username: str) -> str:
    return re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE).strip()


class PotaBot:
    def __init__(self, telegram, ask: Ask, bot_username: str, limiter: RateLimiter):
        self.telegram = telegram
        self.ask = ask
        self.bot_username = bot_username.lstrip("@")
        self.limiter = limiter

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message or not message.get("text"):
            return
        chat_id = message["chat"]["id"]
        user_id = str((message.get("from") or {}).get("id", chat_id))
        reply_to = message.get("message_id")
        text = message["text"]

        command = command_of(text)
        if command is not None:
            if command in COMMANDS:
                await self.telegram.send_message(chat_id, COMMANDS[command], reply_to_message_id=reply_to)
            return

        if not is_addressed_to_bot(message, self.bot_username):
            return
        if not self.limiter.allow(user_id):
            await self.telegram.send_message(chat_id, RATE_LIMIT_TEXT, reply_to_message_id=reply_to)
            return

        question = clean_text(text, self.bot_username)
        if not question:
            await self.telegram.send_message(chat_id, EMPTY_TEXT, reply_to_message_id=reply_to)
            return

        try:
            reply = await self.ask(user_id, f"{chat_id}:{user_id}", question)
        except Exception:
            logger.exception("Errore dell'agente sul messaggio %s", reply_to)
            reply = ERROR_TEXT
        await self.telegram.send_message(chat_id, reply or ERROR_TEXT, reply_to_message_id=reply_to)
```

- [ ] **Step 4: Verifica che passi**

Run: `.venv/bin/pytest tests/test_bot.py -q`
Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add pota_bot/bot.py tests/test_bot.py
git commit -m "PotaBot: menzioni, risposte, comandi /start /help /privacy, limiti ed errori"
```

---

### Task 7: Digest, fonti e notizie recenti

**Files:**
- Create: `pota_bot/data/feeds.json`, `pota_bot/digest.py` (prima parte)
- Test: `tests/test_digest.py` (prima parte)

- [ ] **Step 1: Le fonti** (`pota_bot/data/feeds.json`, tutte verificate con risposta 200 il 16/10/2026):

```json
[
  {"name": "Google Blog · AI", "url": "https://blog.google/technology/ai/rss/"},
  {"name": "Google Developers Blog", "url": "https://developers.googleblog.com/rss/"},
  {"name": "Google Cloud Blog", "url": "https://cloudblog.withgoogle.com/rss/"},
  {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml"},
  {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml"},
  {"name": "TechCrunch · AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"}
]
```

- [ ] **Step 2: Test che fallisce**

```python
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
```

- [ ] **Step 3: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_digest.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pota_bot.digest'`

- [ ] **Step 4: Implementazione (prima parte)**

`pota_bot/digest.py`:
```python
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
```

- [ ] **Step 5: Verifica che passi**

Run: `.venv/bin/pytest tests/test_digest.py -q`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add pota_bot/data/feeds.json pota_bot/digest.py tests/test_digest.py
git commit -m "Digest: fonti RSS e selezione delle notizie della settimana"
```

---

### Task 8: Digest, scrittura con Gemini e verifica dei link

**Files:**
- Modify: `pota_bot/digest.py` (aggiungere in fondo)
- Modify: `tests/test_digest.py` (aggiungere in fondo)

- [ ] **Step 1: Test che falliscono** (in fondo a `tests/test_digest.py`):

```python
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
```

- [ ] **Step 2: Verifica che falliscano**

Run: `.venv/bin/pytest tests/test_digest.py -q`
Expected: FAIL, `ImportError: cannot import name 'build_weekly_digest'`

- [ ] **Step 3: Implementazione** (in fondo a `pota_bot/digest.py`):

```python
import asyncio
from typing import Awaitable, Callable

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
```

Spostare `import asyncio` e `from typing import Awaitable, Callable` in cima al file insieme agli altri import.

- [ ] **Step 4: Verifica che passino**

Run: `.venv/bin/pytest -q`
Expected: tutti passano (`37 passed`)

- [ ] **Step 5: Commit**

```bash
git add pota_bot/digest.py tests/test_digest.py
git commit -m "Digest: scrittura con Gemini, link verificati, versione di riserva senza AI"
```

---

### Task 9: Configurazione e server FastAPI

**Files:**
- Create: `pota_bot/config.py`, `server/__init__.py` (vuoto), `server/main.py`, `server/production.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Test che fallisce**

```python
from fastapi.testclient import TestClient

from pota_bot.config import Settings
from server.main import create_app

SETTINGS = Settings(
    telegram_bot_token="T", telegram_bot_username="pota_test_bot", telegram_webhook_secret="segreto",
    task_token="task", digest_chat_id="-100", use_firestore=False, rate_limit_per_hour=20,
)


class FakeBot:
    def __init__(self):
        self.updates = []

    async def handle_update(self, update):
        self.updates.append(update)


def make_client():
    bot, digests = FakeBot(), []

    async def digest_job():
        digests.append(True)
        return "digest"

    return TestClient(create_app(bot, SETTINGS, digest_job)), bot, digests


def test_healthz():
    client, _, _ = make_client()
    assert client.get("/healthz").json() == {"ok": True}


def test_webhook_rejects_wrong_secret():
    client, bot, _ = make_client()
    r = client.post("/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "no"})
    assert r.status_code == 403 and bot.updates == []


def test_webhook_passes_update_to_bot():
    client, bot, _ = make_client()
    r = client.post("/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "segreto"})
    assert r.status_code == 200 and bot.updates == [{"update_id": 1}]


def test_digest_needs_task_token():
    client, _, digests = make_client()
    assert client.post("/tasks/digest").status_code == 403
    r = client.post("/tasks/digest", headers={"X-Pota-Task-Token": "task"})
    assert r.status_code == 200 and digests == [True]


def test_empty_secret_in_config_rejects_everything():
    from dataclasses import replace
    bot = FakeBot()

    async def digest_job():
        return ""

    client = TestClient(create_app(bot, replace(SETTINGS, telegram_webhook_secret=""), digest_job))
    r = client.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": ""})
    assert r.status_code == 403
```

- [ ] **Step 2: Verifica che fallisca**

Run: `.venv/bin/pytest tests/test_server.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pota_bot.config'`

- [ ] **Step 3: `pota_bot/config.py`**

```python
"""Configurazione del servizio, letta dalle variabili d'ambiente."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_bot_username: str
    telegram_webhook_secret: str
    task_token: str
    digest_chat_id: str
    use_firestore: bool
    rate_limit_per_hour: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_bot_username=os.environ["TELEGRAM_BOT_USERNAME"].lstrip("@"),
            telegram_webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
            task_token=os.environ.get("POTA_TASK_TOKEN", ""),
            digest_chat_id=os.environ.get("TELEGRAM_DIGEST_CHAT_ID", ""),
            use_firestore=os.environ.get("POTA_USE_FIRESTORE", "false").lower() == "true",
            rate_limit_per_hour=int(os.environ.get("POTA_RATE_LIMIT_PER_HOUR", "20")),
        )
```

- [ ] **Step 4: `server/main.py`**

```python
"""Gli endpoint del servizio. `create_app` riceve i pezzi già pronti, così si testa senza cloud."""
import logging
import secrets
from typing import Awaitable, Callable

from fastapi import FastAPI, Header, HTTPException, Request

from pota_bot.config import Settings

logging.basicConfig(level=logging.INFO)


def _same_secret(given: str | None, expected: str) -> bool:
    return bool(expected) and secrets.compare_digest(given or "", expected)


def create_app(bot, settings: Settings, digest_job: Callable[[], Awaitable[str]]) -> FastAPI:
    app = FastAPI(title="Pota Bot")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request,
                               x_telegram_bot_api_secret_token: str | None = Header(default=None)):
        if not _same_secret(x_telegram_bot_api_secret_token, settings.telegram_webhook_secret):
            raise HTTPException(status_code=403)
        # La risposta si genera PRIMA di restituire 200: su Cloud Run, dopo la risposta la CPU viene ridotta.
        await bot.handle_update(await request.json())
        return {"ok": True}

    @app.post("/tasks/digest")
    async def weekly_digest(x_pota_task_token: str | None = Header(default=None)):
        if not _same_secret(x_pota_task_token, settings.task_token):
            raise HTTPException(status_code=403)
        text = await digest_job()
        return {"ok": True, "chars": len(text)}

    return app
```

- [ ] **Step 5: `server/production.py`**

```python
"""Collega i pezzi veri. Avvio: uvicorn server.production:app"""
from pota_bot.agent import build_agent
from pota_bot.bot import PotaBot
from pota_bot.chat import AgentChat
from pota_bot.config import Settings
from pota_bot.digest import build_weekly_digest, gemini_generate
from pota_bot.ratelimit import RateLimiter
from pota_bot.storage import FirestoreProposalStore, MemoryProposalStore
from pota_bot.telegram import TelegramClient
from server.main import create_app

settings = Settings.from_env()
store = FirestoreProposalStore() if settings.use_firestore else MemoryProposalStore()
telegram = TelegramClient(settings.telegram_bot_token)
bot = PotaBot(
    telegram=telegram,
    ask=AgentChat(build_agent(store)).ask,
    bot_username=settings.telegram_bot_username,
    limiter=RateLimiter(settings.rate_limit_per_hour),
)


async def digest_job() -> str:
    text = await build_weekly_digest(gemini_generate)
    if text and settings.digest_chat_id:
        await telegram.send_message(settings.digest_chat_id, text)
    return text


app = create_app(bot, settings, digest_job)
```

- [ ] **Step 6: Verifica che passino tutti**

Run: `.venv/bin/pytest -q`
Expected: tutti passano (`42 passed`)

- [ ] **Step 7: Commit**

```bash
git add pota_bot/config.py server/ tests/test_server.py
git commit -m "Server: endpoint webhook, digest e healthz con verifica dei segreti"
```

---

### Task 10: Prova in locale su Telegram (gruppo finto)

**Prerequisiti (Nicola):** bot di test creato con @BotFather, gruppo finto con il bot dentro, e `pota_bot/.env` con:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_BOT_USERNAME=...        # senza @
GOOGLE_API_KEY=...               # chiave AI Studio, free tier va bene per le prove
GOOGLE_GENAI_USE_VERTEXAI=FALSE
TELEGRAM_DIGEST_CHAT_ID=         # lo scopre lo script al primo messaggio nel gruppo
```

**Files:**
- Create: `scripts/run_polling.py`

- [ ] **Step 1: Script**

```python
"""Pota Bot in locale, senza cloud: legge i messaggi con il polling.

Uso:
  .venv/bin/python scripts/run_polling.py            # il bot risponde su Telegram
  .venv/bin/python scripts/run_polling.py --digest   # genera il digest e lo manda a TELEGRAM_DIGEST_CHAT_ID
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "pota_bot" / ".env")

from pota_bot.agent import build_agent  # noqa: E402
from pota_bot.bot import PotaBot  # noqa: E402
from pota_bot.chat import AgentChat  # noqa: E402
from pota_bot.digest import build_weekly_digest, gemini_generate  # noqa: E402
from pota_bot.ratelimit import RateLimiter  # noqa: E402
from pota_bot.storage import MemoryProposalStore  # noqa: E402
from pota_bot.telegram import TelegramClient  # noqa: E402

logging.basicConfig(level=logging.INFO)


async def run_bot(telegram: TelegramClient) -> None:
    bot = PotaBot(telegram, AgentChat(build_agent(MemoryProposalStore())).ask,
                  os.environ["TELEGRAM_BOT_USERNAME"], RateLimiter(20))
    await telegram.delete_webhook()  # il polling non funziona se c'è un webhook attivo
    print("✅ Pota Bot in ascolto. Scrivigli su Telegram (Ctrl+C per fermare).")
    offset = 0
    while True:
        for update in await telegram.get_updates(offset=offset):
            offset = update["update_id"] + 1
            chat = (update.get("message") or {}).get("chat") or {}
            print(f"📨 chat {chat.get('id')} ({chat.get('type')}): {(update.get('message') or {}).get('text')}")
            await bot.handle_update(update)


async def send_digest(telegram: TelegramClient) -> None:
    text = await build_weekly_digest(gemini_generate)
    print(text or "(nessuna notizia questa settimana)")
    chat_id = os.environ.get("TELEGRAM_DIGEST_CHAT_ID")
    if text and chat_id:
        await telegram.send_message(chat_id, text)
        print(f"✅ Digest inviato alla chat {chat_id}")


if __name__ == "__main__":
    client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
    asyncio.run(send_digest(client) if "--digest" in sys.argv else run_bot(client))
```

- [ ] **Step 2: Prova manuale della chat** (`.venv/bin/python scripts/run_polling.py`), su Telegram, e spuntare:
  - [ ] in privato: "quando è il prossimo evento?" → risposta con la data, citata dal bot
  - [ ] nel gruppo, senza menzione: nessuna risposta
  - [ ] nel gruppo, `@<bot> quanto costano gli eventi?` → risposta come reply
  - [ ] rispondendo a un messaggio del bot, senza menzione → risposta
  - [ ] `/privacy` → testo privacy
  - [ ] proposta con email → rifiutata
  - [ ] "chi vince il campionato di calcio?" → risposta "fuori tema"
  - [ ] dal log, copiare l'id del gruppo (numero negativo) in `TELEGRAM_DIGEST_CHAT_ID` nel `.env`

> ⚠️ Se nel gruppo il bot non vede le menzioni: in @BotFather → `/setprivacy` → Disable **non** serve per menzioni e reply; serve solo per leggere tutti i messaggi. Lasciarla attiva (Enable) è più rispettoso della privacy.

- [ ] **Step 3: Prova manuale del digest** (`.venv/bin/python scripts/run_polling.py --digest`):
  - [ ] il testo arriva nel gruppo finto
  - [ ] ogni notizia ha un link che si apre ed è una notizia della settimana
  - [ ] il log non mostra "versione di riserva" (se la mostra: annotare i problemi, va bene comunque)

- [ ] **Step 4: Commit**

```bash
git add scripts/run_polling.py
git commit -m "Script per provare il bot in locale con il polling e inviare il digest"
```

---

### Task 11: Container

**Files:**
- Create: `Dockerfile`, `.dockerignore`

- [ ] **Step 1: `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 GOOGLE_GENAI_USE_VERTEXAI=FALSE
COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt
COPY pota_bot ./pota_bot
COPY server ./server
CMD exec uvicorn server.production:app --host 0.0.0.0 --port ${PORT:-8080}
```

`.dockerignore`:
```
.venv
.git
**/__pycache__
**/.env
tests
docs
scripts
deploy
workshop.ipynb
```

- [ ] **Step 2: Build e avvio in locale**

Run:
```bash
docker build -t pota-bot:local . && docker run --rm -d --name pota-bot-local -p 8080:8080 \
  --env-file pota_bot/.env -e TELEGRAM_WEBHOOK_SECRET=prova -e POTA_TASK_TOKEN=prova pota-bot:local
sleep 5 && curl -s localhost:8080/healthz
```
Expected: `{"ok":true}`

- [ ] **Step 3: Verifica dei segreti nel container**

Run:
```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8080/telegram/webhook -d '{}'
curl -s -X POST localhost:8080/telegram/webhook -H 'X-Telegram-Bot-Api-Secret-Token: prova' \
  -H 'Content-Type: application/json' -d '{"update_id":1}'
docker stop pota-bot-local
```
Expected: `403`, poi `{"ok":true}`

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "Container per Cloud Run"
```

---

### Task 12: Script di deploy e smontaggio

**Files:**
- Create: `deploy/config.env.example`, `deploy/deploy.sh`, `deploy/teardown.sh`
- Modify: `.gitignore` (aggiungere `deploy/config.env`)

- [ ] **Step 1: `deploy/config.env.example`**

```bash
# Copia in deploy/config.env (escluso da git) e compila.
PROJECT_ID=                       # il progetto Google Cloud di GDG Brescia (NON un progetto di lavoro)
REGION=europe-west8               # Cloud Run: Milano
SCHEDULER_REGION=europe-west1     # Cloud Scheduler
FIRESTORE_LOCATION=eur3           # Firestore: multi-regione europea
SERVICE=pota-bot
TELEGRAM_BOT_USERNAME=            # senza @
TELEGRAM_DIGEST_CHAT_ID=          # id del gruppo (numero negativo)
DIGEST_SCHEDULE="0 9 * * 1"       # ogni lunedì alle 9:00
```

Aggiungere a `.gitignore` la riga `deploy/config.env`.

- [ ] **Step 2: `deploy/deploy.sh`**

```bash
#!/usr/bin/env bash
# Deploy di Pota Bot su Google Cloud, da zero o in aggiornamento.
# Uso: ./deploy/deploy.sh   (legge deploy/config.env)
# Al primo avvio chiede token Telegram e chiave Gemini (oppure: TELEGRAM_BOT_TOKEN=... GEMINI_API_KEY=... ./deploy/deploy.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.env
: "${PROJECT_ID:?Manca PROJECT_ID in deploy/config.env}"
: "${TELEGRAM_BOT_USERNAME:?Manca TELEGRAM_BOT_USERNAME}"
: "${TELEGRAM_DIGEST_CHAT_ID:?Manca TELEGRAM_DIGEST_CHAT_ID}"

G="gcloud --project=$PROJECT_ID --quiet"
SA="pota-bot@${PROJECT_ID}.iam.gserviceaccount.com"
step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$1"; }

secret_exists() { $G secrets describe "$1" >/dev/null 2>&1; }
create_secret() { printf '%s' "$2" | $G secrets create "$1" --data-file=- --replication-policy=automatic >/dev/null; }
ask_secret() {  # nome, variabile d'ambiente, domanda
  secret_exists "$1" && return
  local value="${!2:-}"
  if [ -z "$value" ]; then read -r -s -p "$3: " value; echo; fi
  create_secret "$1" "$value"
}

step "1/7 Abilito le API"
$G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com

step "2/7 Firestore"
$G firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  $G firestore databases create --location="$FIRESTORE_LOCATION" --type=firestore-native

step "3/7 Segreti in Secret Manager"
ask_secret pota-telegram-token TELEGRAM_BOT_TOKEN "Token del bot Telegram"
ask_secret pota-gemini-key GEMINI_API_KEY "Chiave API Gemini"
secret_exists pota-webhook-secret || create_secret pota-webhook-secret "$(openssl rand -hex 24)"
secret_exists pota-task-token || create_secret pota-task-token "$(openssl rand -hex 24)"

step "4/7 Service account con i permessi minimi"
$G iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  $G iam service-accounts create pota-bot --display-name="Pota Bot"
for role in roles/datastore.user roles/secretmanager.secretAccessor; do
  $G projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role" --condition=None >/dev/null
done

step "5/7 Build e deploy su Cloud Run (2-4 minuti)"
$G run deploy "$SERVICE" --source . --region "$REGION" --service-account "$SA" \
  --allow-unauthenticated --min-instances 0 --max-instances 1 --memory 1Gi --timeout 120 \
  --set-env-vars "TELEGRAM_BOT_USERNAME=$TELEGRAM_BOT_USERNAME,TELEGRAM_DIGEST_CHAT_ID=$TELEGRAM_DIGEST_CHAT_ID,POTA_USE_FIRESTORE=true" \
  --set-secrets "TELEGRAM_BOT_TOKEN=pota-telegram-token:latest,GOOGLE_API_KEY=pota-gemini-key:latest,TELEGRAM_WEBHOOK_SECRET=pota-webhook-secret:latest,POTA_TASK_TOKEN=pota-task-token:latest"
URL=$($G run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
curl -fsS "$URL/healthz" >/dev/null && echo "Servizio attivo: $URL"

step "6/7 Collego Telegram al servizio (webhook)"
TOKEN=$($G secrets versions access latest --secret=pota-telegram-token)
WEBHOOK_SECRET=$($G secrets versions access latest --secret=pota-webhook-secret)
curl -fsS -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  --data-urlencode "url=${URL}/telegram/webhook" --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message"]' | grep -q '"ok":true' && echo "Webhook impostato"

step "7/7 Digest settimanale con Cloud Scheduler"
TASK_TOKEN=$($G secrets versions access latest --secret=pota-task-token)
JOB_ARGS=(--location "$SCHEDULER_REGION" --schedule "$DIGEST_SCHEDULE" --time-zone "Europe/Rome"
  --uri "$URL/tasks/digest" --http-method POST)
if $G scheduler jobs describe pota-bot-digest --location "$SCHEDULER_REGION" >/dev/null 2>&1; then
  $G scheduler jobs update http pota-bot-digest "${JOB_ARGS[@]}" --update-headers "X-Pota-Task-Token=$TASK_TOKEN"
else
  $G scheduler jobs create http pota-bot-digest "${JOB_ARGS[@]}" --headers "X-Pota-Task-Token=$TASK_TOKEN"
fi

printf '\n\033[1;32m✅ Pota Bot è online: %s\033[0m\n' "$URL"
echo "Digest subito: $G scheduler jobs run pota-bot-digest --location $SCHEDULER_REGION"
```

- [ ] **Step 3: `deploy/teardown.sh`**

```bash
#!/usr/bin/env bash
# Smonta il servizio (per rifare il deploy da zero nel webinar).
# NON tocca segreti e Firestore: le proposte salvate restano.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.env
G="gcloud --project=$PROJECT_ID --quiet"

TOKEN=$($G secrets versions access latest --secret=pota-telegram-token)
curl -fsS -X POST "https://api.telegram.org/bot${TOKEN}/deleteWebhook" >/dev/null && echo "Webhook rimosso"
$G scheduler jobs delete pota-bot-digest --location "$SCHEDULER_REGION" 2>/dev/null && echo "Job del digest rimosso" || true
$G run services delete "$SERVICE" --region "$REGION" 2>/dev/null && echo "Servizio Cloud Run rimosso" || true
echo "✅ Smontato. Per ripartire: ./deploy/deploy.sh"
```

- [ ] **Step 4: Controllo sintassi**

Run: `chmod +x deploy/*.sh && bash -n deploy/deploy.sh && bash -n deploy/teardown.sh && echo ok`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add deploy/ .gitignore
git commit -m "Deploy: script per Cloud Run, Firestore, Secret Manager, Scheduler e webhook"
```

---

### Task 13: Prova generale su Google Cloud (gruppo finto)

**Prerequisiti:** progetto creato da Matteo, fatturazione attiva, account **personale/GDG** di Nicola con ruolo Owner. Login dedicato, senza toccare la configurazione di lavoro:
```bash
gcloud config configurations create gdg-brescia
gcloud auth login            # con l'account personale/GDG
gcloud config set project <PROJECT_ID>
```
(per tornare alla configurazione di lavoro: `gcloud config configurations activate default`)

- [ ] **Step 1:** `cp deploy/config.env.example deploy/config.env` e compilarlo (bot e gruppo **di test**).
- [ ] **Step 2:** Avviso di budget a 5 € sul billing del progetto (Console → Fatturazione → Budget e avvisi).
- [ ] **Step 3:** `./deploy/deploy.sh` → annotare i tempi di ogni passo (serviranno per il webinar).
- [ ] **Step 4:** Ripetere sul gruppo finto la checklist del Task 10 Step 2 (ora passa da Cloud Run).
- [ ] **Step 5:** Proposta valida dal gruppo → compare in Firestore (Console → Firestore → `proposals`).
- [ ] **Step 6:** `gcloud --project=$PROJECT_ID scheduler jobs run pota-bot-digest --location europe-west1` → il digest arriva nel gruppo.
- [ ] **Step 7:** Log senza errori: `gcloud --project=$PROJECT_ID run services logs read pota-bot --region europe-west8 --limit 50`.
- [ ] **Step 8:** `./deploy/teardown.sh` e poi di nuovo `./deploy/deploy.sh` (è la sequenza del webinar): tutto torna a funzionare.
- [ ] **Step 9:** Annotare in `docs/DEPLOY.md` (Task 14) i tempi reali e ogni intoppo trovato.

---

### Task 14: Guida per il webinar e README

**Files:**
- Create: `docs/DEPLOY.md`
- Modify: `README.md` (sezione "Deploy")

- [ ] **Step 1: `docs/DEPLOY.md`**, con queste sezioni (testo completo da scrivere con i tempi reali del Task 13):
  1. **Prima del webinar (il giorno prima):** login gcloud nella configurazione `gdg-brescia`; `./deploy/teardown.sh` per partire da zero; bot e gruppo finto aperti su Telegram; terminale con font grande; console Cloud aperta su Cloud Run, Firestore, Scheduler.
  2. **Scaletta del deploy dal vivo:** per ognuno dei 7 passi di `deploy.sh`: cosa fa, cosa dire ("il segreto del webhook impedisce a chiunque di far parlare il bot"), cosa mostrare nella console, durata misurata.
  3. **Demo dopo il deploy:** le domande da fare nel gruppo, in ordine (evento, FAQ, news, proposta valida → Firestore, proposta con email → bloccata, fuori tema → bloccata, digest lanciato a mano).
  4. **Piano B:** se il build è lento → mostrare il servizio già deployato in un secondo progetto o una registrazione; se Gemini dà 429 → spiegare quote e tier; se Telegram non risponde → `getWebhookInfo` (`curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`).
  5. **Passare al gruppo vero:** chiave Gemini **a pagamento** in `pota-gemini-key` (`gcloud secrets versions add`), nuovo `TELEGRAM_DIGEST_CHAT_ID`, bot aggiunto al gruppo, `./deploy/deploy.sh`.

- [ ] **Step 2: `README.md`**: aggiungere sotto "Provalo in locale" una sezione "Su Telegram e in produzione" con link a `docs/design.md` e `docs/DEPLOY.md` e i due comandi `scripts/run_polling.py` e `deploy/deploy.sh`.

- [ ] **Step 3: Commit**

```bash
git add docs/DEPLOY.md README.md
git commit -m "Guida del deploy per il webinar e README"
```

---

## Ordine e dipendenze

- Task 0–9 e 11–12: **subito**, non servono token né cloud.
- Task 10: serve il **bot di test e la chiave Gemini** (Nicola).
- Task 13: serve il **progetto Google Cloud** (Matteo).
- Task 14: dopo il Task 13 (servono i tempi reali). Entro **martedì 20 ottobre**, per un webinar a fine settimana.
