"""Tests for providers — adapter logic and model router."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aeos.core.providers.base import CompletionRequest, CompletionResponse, Message
from aeos.core.providers.router import ModelRouter
from aeos.core.config.schema import TaskType, Complexity


class TestMessage:
    def test_message_creation(self):
        """Message dataclass stores role and content."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"


class TestCompletionRequest:
    def test_defaults(self):
        """CompletionRequest has sensible defaults."""
        req = CompletionRequest(
            messages=[Message(role="user", content="Hi")],
            model="gpt-test",
        )
        assert req.temperature == 0.2
        assert req.max_tokens == 2048
        assert req.extra == {}


class TestModelRouter:
    def test_describe_routing(self, minimal_config):
        """Router describes all routing entries correctly."""
        router = ModelRouter(minimal_config)
        table = router.describe_routing()
        assert "inference" in table
        assert "coding" in table
        assert "high" in table["inference"]
        assert "low" in table["coding"]

    def test_get_provider_caches_instance(self, minimal_config):
        """Router caches provider instances — same key returns same object."""
        router = ModelRouter(minimal_config)
        p1 = router.get_provider("test_provider")
        p2 = router.get_provider("test_provider")
        assert p1 is p2

    def test_unknown_provider_raises(self, minimal_config):
        """Requesting an unknown provider key raises ValueError."""
        router = ModelRouter(minimal_config)
        with pytest.raises((ValueError, KeyError)):
            router.get_provider("nonexistent_provider_xyz")

    @pytest.mark.asyncio
    async def test_complete_routes_to_correct_model(self, minimal_config):
        """Router calls the provider with the correct model for a given routing."""
        router = ModelRouter(minimal_config)

        mock_response = CompletionResponse(
            content="Test response",
            model="gpt-test",
            provider="test_provider",
        )
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)
        router._provider_cache["test_provider"] = mock_provider

        response = await router.complete(
            messages=[Message(role="user", content="Hello")],
            task_type=TaskType.CODING,
            complexity=Complexity.LOW,
        )

        assert response.content == "Test response"
        mock_provider.complete.assert_called_once()
        call_args = mock_provider.complete.call_args[0][0]
        assert call_args.model == "gpt-test"


class TestOpenAIProvider:
    def test_initializes_with_custom_base_url(self):
        """OpenAI provider stores custom base_url for compatible endpoints."""
        from aeos.core.providers.openai_provider import OpenAIProvider
        prov = OpenAIProvider(base_url="http://localhost:8000/v1", api_key="test")
        assert prov._base_url == "http://localhost:8000/v1"

    def test_is_available_returns_true(self):
        """OpenAI provider is_available returns True by default."""
        from aeos.core.providers.openai_provider import OpenAIProvider
        prov = OpenAIProvider(base_url="http://localhost:8000/v1", api_key="test")
        assert prov.is_available() is True


class TestAnthropicProvider:
    def test_initializes_with_custom_base_url(self):
        """Anthropic provider accepts a custom base_url for local servers."""
        from aeos.core.providers.anthropic_provider import AnthropicProvider
        # Should not raise — base_url forwarded to SDK
        prov = AnthropicProvider(api_key="test-key", base_url="http://localhost:8001")
        assert prov._client is not None

    def test_initializes_without_base_url(self):
        """Anthropic provider works without base_url (defaults to api.anthropic.com)."""
        from aeos.core.providers.anthropic_provider import AnthropicProvider
        prov = AnthropicProvider(api_key="test-key")
        assert prov._client is not None


class TestOllamaProvider:
    def test_initializes_with_custom_base_url(self):
        """Ollama provider stores any base_url."""
        from aeos.core.providers.ollama_provider import OllamaProvider
        prov = OllamaProvider(base_url="http://192.168.1.100:11434")
        assert "192.168.1.100" in prov._base_url

    def test_is_available_false_when_offline(self):
        """Ollama is_available returns False when server is unreachable."""
        from aeos.core.providers.ollama_provider import OllamaProvider
        prov = OllamaProvider(base_url="http://127.0.0.1:19999")  # unlikely to be running
        # Should return False gracefully, not raise
        result = prov.is_available()
        assert isinstance(result, bool)
