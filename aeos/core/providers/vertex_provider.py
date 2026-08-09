"""Google Vertex AI provider (Gemini models)."""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from aeos.core.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
)


class VertexAIProvider(LLMProvider):
    name = "vertex_ai"

    def __init__(
        self,
        project: str,
        location: str = "us-central1",
        **_: object,
    ) -> None:
        self._project = project
        self._location = location
        self._client = None  # initialized lazily

    def _get_client(self):
        if self._client is None:
            try:
                import vertexai  # type: ignore
                from vertexai.generative_models import GenerativeModel  # type: ignore

                vertexai.init(project=self._project, location=self._location)
                self._GenerativeModel = GenerativeModel
            except ImportError as e:
                raise ImportError(
                    "Vertex AI support requires the 'vertex' extra: "
                    "pip install 'aeos[vertex]'"
                ) from e
        return self._GenerativeModel

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        import asyncio

        GenerativeModel = self._get_client()

        # Build prompt: concatenate system + user messages into a single string
        # (Vertex Gemini supports multi-turn but we use a flat format for simplicity)
        parts = []
        for m in request.messages:
            if m.role == "system":
                parts.append(f"[SYSTEM]\n{m.content}")
            elif m.role == "user":
                parts.append(f"[USER]\n{m.content}")
            else:
                parts.append(f"[ASSISTANT]\n{m.content}")
        full_prompt = "\n\n".join(parts)

        model = GenerativeModel(request.model)
        # Run blocking SDK call in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: model.generate_content(full_prompt)
        )
        content = response.text if hasattr(response, "text") else str(response)
        return CompletionResponse(
            content=content,
            model=request.model,
            provider=self.name,
            raw=response,
        )

    def is_available(self) -> bool:
        try:
            import vertexai  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False
