"""Test suite for AEOS — tests run before implementation (TDD Red baseline).

This conftest sets up shared fixtures for all test modules.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import pytest
import yaml

# ── async support ────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Provide a session-scoped event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── minimal config fixture ───────────────────────────────────
_MINIMAL_CONFIG = {
    "providers": {
        "test_provider": {
            "type": "openai",
            "base_url": "http://localhost:9999/v1",
            "api_key": "test-key",
        }
    },
    "routing": {
        "inference": {
            "high":   {"provider": "test_provider", "model": "gpt-test"},
            "medium": {"provider": "test_provider", "model": "gpt-test"},
            "low":    {"provider": "test_provider", "model": "gpt-test"},
        },
        "coding": {
            "high":   {"provider": "test_provider", "model": "gpt-test"},
            "medium": {"provider": "test_provider", "model": "gpt-test"},
            "low":    {"provider": "test_provider", "model": "gpt-test"},
        },
    },
    "project": {
        "workspace_dir": ".aeos_test",
        "max_retries": 1,
        "ask_on_critical": False,
        "decompose_threshold": 100,
    },
}


@pytest.fixture
def minimal_config():
    from aeos.core.config.schema import AEOSConfig
    return AEOSConfig.model_validate(_MINIMAL_CONFIG)


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """A temporary .aeos workspace directory."""
    ws = tmp_path / ".aeos_test"
    ws.mkdir()
    return ws


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Write minimal config YAML to a temp file and return its path."""
    cfg_path = tmp_path / "config.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(_MINIMAL_CONFIG, f)
    return cfg_path


@pytest.fixture
def fresh_state(tmp_workspace: Path):
    """A fresh AEOSState for testing."""
    from aeos.core.state.schema import AEOSState
    return AEOSState(
        objective="Test objective",
        project_root=str(tmp_workspace.parent),
    )


@pytest.fixture
def state_manager(tmp_workspace: Path):
    from aeos.core.state.manager import StateManager
    return StateManager(tmp_workspace)
