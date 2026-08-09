"""Tests for config schema and loader."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from aeos.core.config.schema import (
    AEOSConfig,
    Complexity,
    TaskType,
    ProviderType,
    ModelTarget,
)


# ── Schema validation ────────────────────────────────────────

class TestProviderConfig:
    def test_openai_default_base_url(self, minimal_config):
        """OpenAI provider should default base_url to api.openai.com."""
        from aeos.core.config.schema import ProviderConfig, ProviderType
        prov = ProviderConfig(type=ProviderType.OPENAI)
        assert prov.base_url == "https://api.openai.com/v1"

    def test_openai_custom_base_url(self):
        """OpenAI provider accepts any base_url for compatible endpoints."""
        from aeos.core.config.schema import ProviderConfig
        prov = ProviderConfig(type=ProviderType.OPENAI, base_url="http://localhost:8000/v1")
        assert prov.base_url == "http://localhost:8000/v1"

    def test_anthropic_custom_base_url(self):
        """Anthropic provider accepts a custom base_url for local servers."""
        from aeos.core.config.schema import ProviderConfig
        prov = ProviderConfig(type=ProviderType.ANTHROPIC, base_url="http://my-host:8001")
        assert prov.base_url == "http://my-host:8001"

    def test_ollama_provider(self):
        """Ollama provider accepts base_url pointing to any host."""
        from aeos.core.config.schema import ProviderConfig
        prov = ProviderConfig(
            type=ProviderType.OLLAMA,
            base_url="http://192.168.1.100:11434",
            models=["mistral", "codellama:7b"],
        )
        assert prov.base_url == "http://192.168.1.100:11434"
        assert "mistral" in prov.models

    def test_vertex_requires_project(self):
        """Vertex AI provider must have a project field."""
        from aeos.core.config.schema import ProviderConfig
        with pytest.raises(ValueError, match="project"):
            ProviderConfig(type=ProviderType.VERTEX_AI)

    def test_vertex_with_project(self):
        """Vertex AI provider with project is valid."""
        from aeos.core.config.schema import ProviderConfig
        prov = ProviderConfig(type=ProviderType.VERTEX_AI, project="my-gcp-project")
        assert prov.project == "my-gcp-project"


class TestRoutingConfig:
    def test_resolve_inference_high(self, minimal_config):
        """Routing should resolve inference/high to the correct provider+model."""
        target = minimal_config.routing.resolve(TaskType.INFERENCE, Complexity.HIGH)
        assert isinstance(target, ModelTarget)
        assert target.provider == "test_provider"
        assert target.model == "gpt-test"

    def test_resolve_coding_low(self, minimal_config):
        """Routing should resolve coding/low correctly."""
        target = minimal_config.routing.resolve(TaskType.CODING, Complexity.LOW)
        assert target.provider == "test_provider"

    def test_resolve_unknown_task_type_falls_back_to_inference(self, minimal_config):
        """Unspecified task types should fall back to inference routing."""
        target = minimal_config.routing.resolve(TaskType.PLANNING, Complexity.MEDIUM)
        assert target.provider == "test_provider"

    def test_routing_validates_provider_exists(self):
        """Config should raise if routing references an undefined provider."""
        bad_config = {
            "providers": {
                "real_provider": {
                    "type": "openai",
                    "base_url": "http://localhost/v1",
                    "api_key": "k",
                }
            },
            "routing": {
                "inference": {
                    "high":   {"provider": "nonexistent_provider", "model": "m"},
                    "medium": {"provider": "real_provider", "model": "m"},
                    "low":    {"provider": "real_provider", "model": "m"},
                },
                "coding": {
                    "high":   {"provider": "real_provider", "model": "m"},
                    "medium": {"provider": "real_provider", "model": "m"},
                    "low":    {"provider": "real_provider", "model": "m"},
                },
            },
        }
        with pytest.raises(ValueError, match="nonexistent_provider"):
            AEOSConfig.model_validate(bad_config)


class TestConfigLoader:
    def test_load_from_file(self, config_file: Path):
        """Loader should parse a valid config file."""
        from aeos.core.config.loader import load_config
        config = load_config(config_path=config_file)
        assert isinstance(config, AEOSConfig)
        assert "test_provider" in config.providers

    def test_load_missing_file_raises(self, tmp_path: Path):
        """Loader should raise FileNotFoundError when no config exists."""
        from aeos.core.config.loader import load_config
        with pytest.raises(FileNotFoundError):
            load_config(config_path=tmp_path / "nonexistent.yaml", cwd=tmp_path)

    def test_env_var_injection(self, tmp_path: Path, monkeypatch):
        """Loader should inject env var values as api_key."""
        monkeypatch.setenv("MY_TEST_KEY", "sk-injected-key")
        cfg_data = {
            "providers": {
                "cloud": {
                    "type": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key_env": "MY_TEST_KEY",
                }
            },
            "routing": {
                "inference": {
                    "high":   {"provider": "cloud", "model": "gpt-4o"},
                    "medium": {"provider": "cloud", "model": "gpt-4o"},
                    "low":    {"provider": "cloud", "model": "gpt-4o"},
                },
                "coding": {
                    "high":   {"provider": "cloud", "model": "gpt-4o"},
                    "medium": {"provider": "cloud", "model": "gpt-4o"},
                    "low":    {"provider": "cloud", "model": "gpt-4o"},
                },
            },
        }
        cfg_path = tmp_path / "env_test.yaml"
        with open(cfg_path, "w") as f:
            yaml.dump(cfg_data, f)

        from aeos.core.config.loader import load_config
        config = load_config(config_path=cfg_path)
        assert config.providers["cloud"].api_key == "sk-injected-key"
