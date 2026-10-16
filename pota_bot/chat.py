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
