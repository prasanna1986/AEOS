"""
aeos init — interactive project initialization wizard.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()

_GLOBAL_CONFIG_DIR = Path.home() / ".aeos"
_EXAMPLE_CONFIG = Path(__file__).parent.parent.parent / "config.example.yaml"


def init_command(
    global_config: bool = typer.Option(
        False, "--global", "-g",
        help="Create/update the global config at ~/.aeos/config.yaml",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
) -> None:
    """
    Initialize AEOS for a project or configure global defaults.

    Guides you through provider selection and model routing setup.
    """
    console.print(
        Panel.fit(
            "[bold cyan]AEOS Init[/] — Autonomous Engineering OS Setup",
            border_style="cyan",
        )
    )

    target_dir = _GLOBAL_CONFIG_DIR if global_config else Path.cwd() / ".aeos"
    config_path = target_dir / "config.yaml"

    if config_path.exists() and not force:
        overwrite = Confirm.ask(
            f"Config already exists at [cyan]{config_path}[/]. Overwrite?",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]Init cancelled.[/]")
            raise typer.Exit()

    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy example config as starting point
    if _EXAMPLE_CONFIG.exists():
        shutil.copy2(_EXAMPLE_CONFIG, config_path)
        console.print(f"[green]✓[/] Created config at [cyan]{config_path}[/]")
    else:
        # Generate minimal config inline
        _write_minimal_config(config_path)
        console.print(f"[green]✓[/] Created minimal config at [cyan]{config_path}[/]")

    # Interactive setup
    console.print("\n[bold]Quick Setup[/] — configure your first provider\n")
    _interactive_setup(config_path)

    # Create project workspace dirs
    for subdir in ["artifacts", "logs", "tests"]:
        (target_dir / subdir).mkdir(exist_ok=True)

    console.print(
        f"\n[bold green]✓ AEOS initialized![/]\n\n"
        f"  [dim]Config:[/]    {config_path}\n"
        f"  [dim]Next steps:[/]\n"
        f"    1. Edit [cyan]{config_path}[/] to add your providers\n"
        f"    2. Set API key environment variables\n"
        f"    3. Run: [bold]aeos run \"<your engineering objective>\"[/]\n"
    )


def _interactive_setup(config_path: Path) -> None:
    """Ask a few key questions and patch the config."""
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Provider preference
    provider_choice = Prompt.ask(
        "Primary provider",
        choices=["anthropic", "openai", "ollama", "vertex_ai", "skip"],
        default="ollama",
    )

    if provider_choice != "skip":
        if provider_choice == "ollama":
            base_url = Prompt.ask("Ollama base URL", default="http://localhost:11434")
            raw.setdefault("providers", {})["local_ollama"] = {
                "type": "ollama",
                "base_url": base_url,
                "models": ["mistral", "codellama:7b"],
            }
            # Minimal routing
            raw.setdefault("routing", {
                "inference": {"high": {"provider": "local_ollama", "model": "mistral"},
                              "medium": {"provider": "local_ollama", "model": "mistral"},
                              "low": {"provider": "local_ollama", "model": "mistral"}},
                "coding": {"high": {"provider": "local_ollama", "model": "codellama:7b"},
                           "medium": {"provider": "local_ollama", "model": "codellama:7b"},
                           "low": {"provider": "local_ollama", "model": "codellama:7b"}},
            })
        elif provider_choice == "anthropic":
            env_var = Prompt.ask("API key environment variable", default="ANTHROPIC_API_KEY")
            base_url = Prompt.ask(
                "Base URL (press Enter for default api.anthropic.com)",
                default="",
            )
            prov: dict = {"type": "anthropic", "api_key_env": env_var}
            if base_url:
                prov["base_url"] = base_url
            raw.setdefault("providers", {})["anthropic_cloud"] = prov
        elif provider_choice == "openai":
            base_url = Prompt.ask("Base URL", default="https://api.openai.com/v1")
            env_var = Prompt.ask("API key environment variable", default="OPENAI_API_KEY")
            raw.setdefault("providers", {})["openai_cloud"] = {
                "type": "openai",
                "base_url": base_url,
                "api_key_env": env_var,
            }
        elif provider_choice == "vertex_ai":
            project = Prompt.ask("GCP project ID")
            location = Prompt.ask("GCP location", default="us-central1")
            raw.setdefault("providers", {})["vertex_ai"] = {
                "type": "vertex_ai",
                "project": project,
                "location": location,
            }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)


def _write_minimal_config(path: Path) -> None:
    minimal = {
        "providers": {
            "local_ollama": {
                "type": "ollama",
                "base_url": "http://localhost:11434",
                "models": ["mistral", "codellama:7b"],
            }
        },
        "routing": {
            "inference": {
                "high": {"provider": "local_ollama", "model": "mistral"},
                "medium": {"provider": "local_ollama", "model": "mistral"},
                "low": {"provider": "local_ollama", "model": "mistral"},
            },
            "coding": {
                "high": {"provider": "local_ollama", "model": "codellama:7b"},
                "medium": {"provider": "local_ollama", "model": "codellama:7b"},
                "low": {"provider": "local_ollama", "model": "codellama:7b"},
            },
        },
        "project": {"workspace_dir": ".aeos", "ask_on_critical": True, "max_retries": 3},
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(minimal, f, default_flow_style=False)
