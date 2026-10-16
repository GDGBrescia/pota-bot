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
    assert llm.script == []


async def test_guardrail_blocks_personal_data_and_nothing_is_saved():
    store = MemoryProposalStore()
    llm = ScriptedLlm(script=[
        ("call", ("propose_topic", {"title": "RAG", "reason": "scrivimi a a@b.it"})),
        ("text", "Non posso salvarla."),
    ])
    events = await run_once(build_agent(store, model=llm), "Propongo RAG, scrivimi a a@b.it")
    assert store.items == []
    assert llm.script == []
    responses = [
        part.function_response.response
        for e in events if e.content
        for part in e.content.parts or []
        if part.function_response and part.function_response.name == "propose_topic"
    ]
    assert [r["status"] for r in responses] == ["rifiutato"]
