"""Configuration schema — Pydantic models for the full AEOS config."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────
# Provider types
# ─────────────────────────────────────────────────────────────

class ProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    VERTEX_AI = "vertex_ai"
    OLLAMA = "ollama"


class ProviderConfig(BaseModel):
    """A single LLM provider definition."""

    type: ProviderType
    # OpenAI / OpenAI-compatible
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None          # inline key (discouraged)
    timeout: int = 120

    # Vertex AI
    project: str | None = None
    location: str = "us-central1"

    # Ollama / LM Studio
    models: list[str] = Field(default_factory=list)
    openai_compat: bool | None = None   # None = auto-detect from base_url

    # Token budget — set these to match your local model's context window.
    # AEOS will cap max_tokens to this value automatically.
    #   context_window: 4096   ← total tokens (prompt + completion)
    #   max_tokens:     2048   ← hard cap on completion tokens sent to this provider
    context_window: int | None = None   # total context window of the model
    max_tokens: int | None = None       # override the per-request max_tokens cap

    # Extra kwargs passed through to the SDK
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_provider(self) -> "ProviderConfig":
        t = self.type
        if t in (ProviderType.OPENAI,) and self.base_url is None:
            self.base_url = "https://api.openai.com/v1"
        if t == ProviderType.VERTEX_AI and self.project is None:
            raise ValueError("vertex_ai provider requires 'project' field")
        return self


# ─────────────────────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────────────────────

class Complexity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskType(str, Enum):
    INFERENCE = "inference"
    CODING = "coding"
    PLANNING = "planning"
    REVIEW = "review"
    VERIFICATION = "verification"


class ModelTarget(BaseModel):
    """A (provider, model) pair for routing."""

    provider: str
    model: str


class ComplexityRouting(BaseModel):
    """Routing table for one task type across three complexity tiers."""

    high: ModelTarget
    medium: ModelTarget
    low: ModelTarget

    def for_complexity(self, complexity: Complexity) -> ModelTarget:
        return getattr(self, complexity.value)


class RoutingConfig(BaseModel):
    """Full routing config across all task types."""

    inference: ComplexityRouting
    coding: ComplexityRouting
    planning: ComplexityRouting | None = None
    review: ComplexityRouting | None = None
    verification: ComplexityRouting | None = None

    def resolve(self, task_type: TaskType, complexity: Complexity) -> ModelTarget:
        """Return the (provider, model) pair for a given task type + complexity."""
        routing = getattr(self, task_type.value, None)
        if routing is None:
            # Fall back to inference routing if not explicitly defined
            routing = self.inference
        return routing.for_complexity(complexity)


# ─────────────────────────────────────────────────────────────
# Project settings
# ─────────────────────────────────────────────────────────────

class ProjectConfig(BaseModel):
    workspace_dir: str = ".aeos"
    max_retries: int = 3
    ask_on_critical: bool = True
    decompose_threshold: int = 300      # max LoC per atomic task
    auto_activate_stages: bool = True
    git_author_name: str = "AEOS Autonomous Agent"
    git_author_email: str = "aeos@localhost"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str | None = ".aeos/aeos.log"


# ─────────────────────────────────────────────────────────────
# Root config
# ─────────────────────────────────────────────────────────────

class AEOSConfig(BaseModel):
    """Root configuration model — validated representation of config.yaml."""

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    routing: RoutingConfig
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @model_validator(mode="after")
    def _validate_routing_providers(self) -> "AEOSConfig":
        """Ensure every model target references an existing provider."""
        all_task_types = [TaskType.INFERENCE, TaskType.CODING, TaskType.PLANNING,
                          TaskType.REVIEW, TaskType.VERIFICATION]
        for tt in all_task_types:
            routing = getattr(self.routing, tt.value, None)
            if routing is None:
                continue
            for cplx in Complexity:
                target = routing.for_complexity(cplx)
                if target.provider not in self.providers:
                    raise ValueError(
                        f"Routing [{tt.value}/{cplx.value}] references unknown "
                        f"provider '{target.provider}'. "
                        f"Available: {list(self.providers.keys())}"
                    )
        return self
