"""Ollama local provider — uses OpenAI-compatible HTTP API."""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from aeos.core.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        **_: object,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._chat_url = f"{self._base_url}/api/chat"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(self._chat_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        return CompletionResponse(
            content=content,
            model=request.model,
            provider=self.name,
            raw=data,
        )

    def is_available(self) -> bool:
        try:
            import httpx as _httpx
            resp = _httpx.get(f"{self._base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False
