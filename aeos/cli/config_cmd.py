"""aeos config — validate and display resolved configuration."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from aeos.core.config.loader import load_config, get_config_path
from aeos.core.config.schema import TaskType, Complexity

console = Console()

config_app = typer.Typer(help="Manage AEOS configuration.", no_args_is_help=True)


@config_app.command("validate")
def validate_command(
    config_file: Path = typer.Option(None, "--config", "-c", help="Path to config file"),
) -> None:
    """Validate the AEOS config file and report any errors."""
    try:
        cfg = load_config(config_path=config_file)
        found = get_config_path()
        console.print(f"[green]✓ Config valid[/] — {found}")
        console.print(f"  Providers: {list(cfg.providers.keys())}")
    except FileNotFoundError as e:
        console.print(f"[red]Config not found:[/] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Config invalid:[/] {e}")
        raise typer.Exit(1)


@config_app.command("show")
def show_command(
    config_file: Path = typer.Option(None, "--config", "-c"),
) -> None:
    """Show resolved configuration including routing table."""
    try:
        cfg = load_config(config_path=config_file)
    except Exception as e:
        console.print(f"[red]Error loading config:[/] {e}")
        raise typer.Exit(1)

    found = get_config_path()
    console.print(Panel.fit(f"[bold]Config source:[/] {found}", border_style="dim"))

    # Providers table
    prov_table = Table(title="Providers", box=box.ROUNDED)
    prov_table.add_column("Key")
    prov_table.add_column("Type")
    prov_table.add_column("Endpoint / Project")
    prov_table.add_column("Auth")

    for key, prov in cfg.providers.items():
        endpoint = prov.base_url or prov.project or "—"
        auth = prov.api_key_env or ("ADC" if prov.type.value == "vertex_ai" else "none")
        prov_table.add_row(key, prov.type.value, str(endpoint), auth)
    console.print(prov_table)

    # Routing table
    routing = cfg.routing.describe_routing()
    route_table = Table(title="Model Routing", box=box.ROUNDED)
    route_table.add_column("Task Type")
    route_table.add_column("High Complexity")
    route_table.add_column("Medium Complexity")
    route_table.add_column("Low Complexity")

    for tt, cplx_map in routing.items():
        route_table.add_row(
            tt,
            cplx_map.get("high", "—"),
            cplx_map.get("medium", "—"),
            cplx_map.get("low", "—"),
        )
    console.print(route_table)

    # Project settings
    console.print(
        Panel(
            f"workspace_dir: {cfg.project.workspace_dir}\n"
            f"max_retries:   {cfg.project.max_retries}\n"
            f"ask_on_critical: {cfg.project.ask_on_critical}\n"
            f"decompose_threshold: {cfg.project.decompose_threshold} LoC\n"
            f"auto_activate_stages: {cfg.project.auto_activate_stages}",
            title="Project Settings",
            border_style="dim",
        )
    )
