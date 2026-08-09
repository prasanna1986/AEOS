"""OpenAI provider — supports OpenAI API and any OpenAI-compatible endpoint."""

from __future__ import annotations

import os

from tenacity import retry, stop_after_attempt, wait_exponential

from aeos.core.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        api_key_env: str | None = None,
        timeout: int = 120,
        **_: object,
    ) -> None:
        from openai import AsyncOpenAI  # lazy import

        resolved_key = api_key or (os.environ.get(api_key_env or "") if api_key_env else None)
        self._client = AsyncOpenAI(
            api_key=resolved_key or "sk-placeholder",
            base_url=base_url,
            timeout=timeout,
        )
        self._base_url = base_url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        resp = await self._client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            **request.extra,
        )
        choice = resp.choices[0]
        return CompletionResponse(
            content=choice.message.content or "",
            model=resp.model,
            provider=self.name,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            raw=resp,
        )

    def is_available(self) -> bool:
        return True  # connectivity checked lazily on first call
