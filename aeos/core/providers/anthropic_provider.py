"""Anthropic Claude provider."""

from __future__ import annotations

import os

from tenacity import retry, stop_after_attempt, wait_exponential

from aeos.core.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        api_key_env: str | None = None,
        base_url: str | None = None,
        timeout: int = 180,
        **_: object,
    ) -> None:
        from anthropic import AsyncAnthropic  # lazy import

        resolved_key = api_key or (os.environ.get(api_key_env or "") if api_key_env else None)
        kwargs: dict = dict(api_key=resolved_key, timeout=timeout)
        # base_url lets you point at any Anthropic-compatible server:
        # local (http://my-host:8001) or remote (https://my-proxy.example.com)
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        # Anthropic separates the system prompt from user messages
        system_prompt = ""
        messages = []
        for m in request.messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                messages.append({"role": m.role, "content": m.content})

        kwargs: dict = dict(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=messages,
            temperature=request.temperature,
        )
        if system_prompt:
            kwargs["system"] = system_prompt
        kwargs.update(request.extra)

        resp = await self._client.messages.create(**kwargs)
        content = "".join(
            block.text for block in resp.content if hasattr(block, "text")
        )
        return CompletionResponse(
            content=content,
            model=resp.model,
            provider=self.name,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp,
        )

    def is_available(self) -> bool:
        return True
