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
