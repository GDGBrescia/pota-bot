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
        if not self.script:
            raise AssertionError("ScriptedLlm: copione finito, il modello è stato chiamato più volte del previsto")
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
