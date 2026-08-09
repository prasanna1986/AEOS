"""Model router -- maps (task_type, complexity) -> provider + LLM call."""

from __future__ import annotations

from aeos.core.config.schema import AEOSConfig, Complexity, TaskType, ProviderType
from aeos.core.providers.base import CompletionRequest, CompletionResponse, LLMProvider

# Fields in ProviderConfig that are schema-level only and must NOT be forwarded
# as kwargs to provider constructors.
_SCHEMA_ONLY_FIELDS = {"type", "extra", "models", "context_window", "max_tokens"}


def _build_provider(provider_key: str, config: AEOSConfig) -> LLMProvider:
    """Instantiate the correct LLMProvider from config."""
    prov_cfg = config.providers[provider_key]
    kwargs = prov_cfg.model_dump(exclude=_SCHEMA_ONLY_FIELDS)
    kwargs.update(prov_cfg.extra)

    match prov_cfg.type:
        case ProviderType.OPENAI:
            from aeos.core.providers.openai_provider import OpenAIProvider
            return OpenAIProvider(**kwargs)
        case ProviderType.ANTHROPIC:
            from aeos.core.providers.anthropic_provider import AnthropicProvider
            return AnthropicProvider(**kwargs)
        case ProviderType.VERTEX_AI:
            from aeos.core.providers.vertex_provider import VertexAIProvider
            return VertexAIProvider(**kwargs)
        case ProviderType.OLLAMA:
            from aeos.core.providers.ollama_provider import OllamaProvider
            return OllamaProvider(**kwargs)
        case _:
            raise ValueError(f"Unknown provider type: {prov_cfg.type}")


class ModelRouter:
    """
    Routes LLM requests to the correct provider + model based on task type
    and complexity, as configured in config.yaml routing section.
    """

    def __init__(self, config: AEOSConfig) -> None:
        self._config = config
        self._provider_cache: dict[str, LLMProvider] = {}

    def get_provider(self, provider_key: str) -> LLMProvider:
        if provider_key not in self._provider_cache:
            self._provider_cache[provider_key] = _build_provider(provider_key, self._config)
        return self._provider_cache[provider_key]

    def _effective_max_tokens(self, provider_key: str, requested: int) -> int:
        """
        Resolve the actual max_tokens value to send in the API request.

        Priority (highest wins):
          1. provider.max_tokens  -- explicit cap set in config.yaml
          2. provider.context_window // 2 -- derived cap when only context_window
                                             is declared (reserves ~half the window
                                             for the prompt; safe for most models)
          3. requested            -- the caller's value, unchanged

        Examples
        --------
        context_window=4096, max_tokens unset
            -> effective = min(requested, 4096 // 2) = min(requested, 2048)

        context_window=4096, max_tokens=1500
            -> effective = min(requested, 1500)        (max_tokens wins)

        neither set
            -> effective = requested                   (no cap applied)
        """
        prov_cfg = self._config.providers.get(provider_key)
        if prov_cfg is None:
            return requested

        if prov_cfg.max_tokens is not None:
            # Explicit cap -- always respected
            return min(requested, prov_cfg.max_tokens)

        if prov_cfg.context_window is not None:
            # Derived cap: reserve half the window for the prompt
            derived = prov_cfg.context_window // 2
            return min(requested, derived)

        return requested

    async def complete(
        self,
        messages: list,
        task_type: TaskType,
        complexity: Complexity,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> CompletionResponse:
        """
        Route a completion request to the appropriate model.

        Args:
            messages:    List of Message objects.
            task_type:   Type of task (inference, coding, planning, review, verification).
            complexity:  Task complexity (high, medium, low).
            temperature: Sampling temperature.
            max_tokens:  Maximum output tokens.  Will be capped by the provider's
                         declared max_tokens limit (see config.yaml ProviderConfig).
        """
        target = self._config.routing.resolve(task_type, complexity)
        provider = self.get_provider(target.provider)

        effective_tokens = self._effective_max_tokens(target.provider, max_tokens)

        request = CompletionRequest(
            messages=messages,
            model=target.model,
            temperature=temperature,
            max_tokens=effective_tokens,
        )
        return await provider.complete(request)

    def describe_routing(self) -> dict[str, dict[str, str]]:
        """Return a human-readable routing table for display."""
        result: dict[str, dict[str, str]] = {}
        for tt in TaskType:
            routing = getattr(self._config.routing, tt.value, None)
            if routing is None:
                continue
            result[tt.value] = {}
            for cplx in Complexity:
                target = routing.for_complexity(cplx)
                result[tt.value][cplx.value] = f"{target.provider} / {target.model}"
        return result
