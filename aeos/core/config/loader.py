"""Config loader -- YAML load, env-var injection, global+project merge."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from aeos.core.config.schema import AEOSConfig

# Locations checked in order (later overrides earlier)
_GLOBAL_CONFIG_PATH = Path.home() / ".aeos" / "config.yaml"
_PROJECT_CONFIG_NAMES = [".aeos/config.yaml", "aeos.yaml", "aeos.config.yaml"]


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _inject_env_vars(raw: dict) -> dict:
    """Walk provider configs and resolve api_key_env -> api_key."""
    providers = raw.get("providers", {})
    for name, prov in providers.items():
        env_var = prov.get("api_key_env")
        if env_var:
            value = os.environ.get(env_var)
            if value:
                prov["api_key"] = value
    return raw


def _find_project_config(cwd: Path | None = None) -> Path | None:
    """Walk up from cwd looking for a project-level config file."""
    search_dir = cwd or Path.cwd()
    for _ in range(10):  # max 10 levels up
        for name in _PROJECT_CONFIG_NAMES:
            candidate = search_dir / name
            if candidate.exists():
                return candidate
        parent = search_dir.parent
        if parent == search_dir:
            break
        search_dir = parent
    return None


def load_config(
    config_path: str | Path | None = None,
    cwd: Path | None = None,
) -> AEOSConfig:
    """
    Load and merge AEOS configuration.

    Resolution order (each layer overrides the previous):
      1. Built-in defaults (Pydantic model defaults)
      2. Global config: ~/.aeos/config.yaml
      3. Project config: .aeos/config.yaml (or aeos.yaml) found by walking up
      4. Explicit --config flag path (if provided)

    Environment variables are injected after merging.
    """
    raw: dict = {}

    # Layer 2: global config
    if _GLOBAL_CONFIG_PATH.exists():
        with open(_GLOBAL_CONFIG_PATH, encoding="utf-8") as f:
            global_raw = yaml.safe_load(f) or {}
        raw = _deep_merge(raw, global_raw)

    # Layer 3: project config
    if config_path is None:
        project_cfg = _find_project_config(cwd)
    else:
        project_cfg = Path(config_path)

    if project_cfg and project_cfg.exists():
        with open(project_cfg, encoding="utf-8") as f:
            project_raw = yaml.safe_load(f) or {}
        raw = _deep_merge(raw, project_raw)

    if not raw:
        raise FileNotFoundError(
            "No AEOS configuration found.\n"
            "Run `aeos init` to create one, or copy config.example.yaml to "
            "~/.aeos/config.yaml"
        )

    # Inject env vars
    raw = _inject_env_vars(raw)

    return AEOSConfig.model_validate(raw)


def get_config_path() -> Path | None:
    """Return the path of the first config file found (for display)."""
    if _GLOBAL_CONFIG_PATH.exists():
        return _GLOBAL_CONFIG_PATH
    return _find_project_config()
