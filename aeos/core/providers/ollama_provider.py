"""Ollama / LM Studio local provider.

Supports two API modes:
  - ``ollama``       -- native Ollama JSON API  (POST /api/chat)
  - ``openai_compat``-- OpenAI-compatible API   (POST /v1/chat/completions)

Auto-detection:
  If ``base_url`` is NOT the default Ollama address (localhost:11434) it is
  almost certainly an OpenAI-compat server (LM Studio, vLLM, llama.cpp...),
  so ``openai_compat`` is selected automatically.  Set ``openai_compat=true``
  explicitly in your provider config to override for any base_url.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from aeos.core.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
)

_DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str = _DEFAULT_OLLAMA_URL,
        openai_compat: bool | None = None,  # None = auto-detect
        **_: object,
    ) -> None:
        self._base_url = base_url.rstrip("/")

        # Auto-detect: if the URL is not the default Ollama address, assume
        # the server speaks the OpenAI-compatible API (LM Studio, vLLM, etc.)
        if openai_compat is None:
            normalized = self._base_url.rstrip("/")
            openai_compat = normalized != _DEFAULT_OLLAMA_URL.rstrip("/")

        self._openai_compat = openai_compat

        if openai_compat:
            # Ensure we have a /v1 base for OpenAI-compat servers
            if not self._base_url.endswith("/v1"):
                self._chat_url = f"{self._base_url}/v1/chat/completions"
            else:
                self._chat_url = f"{self._base_url}/chat/completions"
        else:
            self._chat_url = f"{self._base_url}/api/chat"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self._openai_compat:
            return await self._complete_openai_compat(request)
        return await self._complete_ollama(request)

    async def _complete_ollama(self, request: CompletionRequest) -> CompletionResponse:
        """Native Ollama /api/chat call."""
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

    async def _complete_openai_compat(self, request: CompletionRequest) -> CompletionResponse:
        """OpenAI-compatible /v1/chat/completions call (LM Studio, vLLM, etc.)."""
        payload = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(self._chat_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return CompletionResponse(
            content=content,
            model=data.get("model", request.model),
            provider=self.name,
            raw=data,
        )

    def is_available(self) -> bool:
        try:
            if self._openai_compat:
                # OpenAI-compat servers expose GET /v1/models
                url = self._base_url
                if not url.endswith("/v1"):
                    url = f"{url}/v1"
                resp = httpx.get(f"{url}/models", timeout=3)
            else:
                resp = httpx.get(f"{self._base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False
