"""
AEOS -- Autonomous Engineering Operating System
Root CLI entry point.

Default (no args): launches the interactive REPL -- like Claude CLI.
Type objectives inside, AEOS runs autonomously and asks critical questions inline.

Subcommands (for scripting/CI):
  aeos shell         Launch the interactive REPL explicitly
  aeos run           One-shot run (non-interactive, for CI)
  aeos init          Initialize a project or global config
  aeos status        Show current workflow status and tasks
  aeos resume        Resume an interrupted session
  aeos log           Show decision log and lessons learned
  aeos config show   Display resolved configuration
  aeos config validate  Validate config file
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from aeos.cli.init_cmd import init_command
from aeos.cli.run import run_command
from aeos.cli.status import status_command
from aeos.cli.config_cmd import config_app
from aeos.cli.repl import AEOSRepl

app = typer.Typer(
    name="aeos",
    help="[bold cyan]AEOS[/] -- Autonomous Engineering Operating System\n\n"
         "Run [bold]aeos[/] with no arguments to enter the interactive shell.\n"
         "Type your engineering objective inside -- AEOS runs autonomously.",
    rich_markup_mode="rich",
    no_args_is_help=False,   # ? allow no-arg invocation to launch REPL
    invoke_without_command=True,
    pretty_exceptions_enable=True,
)

console = Console()

# Register commands
app.command("init", help="Initialize AEOS for a project or configure global defaults.")(init_command)
app.command("run", help="One-shot non-interactive run (use for CI/scripts).")(run_command)
app.command("status", help="Show current workflow stage, tasks, and progress.")(status_command)
app.add_typer(config_app, name="config")


@app.callback(invoke_without_command=True)
def default_callback(
    ctx: typer.Context,
    project_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Project directory"),
    config_file: Path = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """
    Launch the AEOS interactive shell when no subcommand is given.

    This is the primary way to use AEOS -- type your objective inside
    and AEOS runs autonomously, asking critical questions inline.
    """
    if ctx.invoked_subcommand is None:
        # No subcommand -> launch interactive REPL
        repl = AEOSRepl(project_dir=project_dir, config_file=config_file)
        repl.run()


@app.command("resume")
def resume_command(
    project_dir: Path = typer.Option(Path("."), "--dir", "-d"),
    config_file: Path = typer.Option(None, "--config", "-c"),
) -> None:
    """Resume an interrupted AEOS session from the exact point of interruption."""
    from aeos.core.config.loader import load_config
    from aeos.core.state.manager import StateManager

    try:
        config = load_config(config_path=config_file, cwd=project_dir)
    except FileNotFoundError:
        console.print("[red]No config found. Run `aeos init` first.[/]")
        raise typer.Exit(1)

    workspace = project_dir / config.project.workspace_dir
    sm = StateManager(workspace)

    if not sm.exists():
        console.print("[yellow]No session to resume. Run `aeos run \"<objective>\"` first.[/]")
        raise typer.Exit()

    state = sm.load()
    console.print(f"[green]Resuming session {state.session_id} from stage: {state.current_stage}[/]")

    # Re-run via run_command with resume=True
    run_command(
        objective=state.objective,
        project_dir=project_dir,
        config_file=config_file,
        resume=True,
        yes=True,
    )


@app.command("log")
def log_command(
    project_dir: Path = typer.Option(Path("."), "--dir", "-d"),
    config_file: Path = typer.Option(None, "--config", "-c"),
    show_decisions: bool = typer.Option(True, "--decisions/--no-decisions"),
    show_lessons: bool = typer.Option(True, "--lessons/--no-lessons"),
    show_failures: bool = typer.Option(True, "--failures/--no-failures"),
) -> None:
    """Show the decision log, lessons learned, and failure history."""
    from aeos.core.config.loader import load_config
    from aeos.core.state.manager import StateManager

    try:
        config = load_config(config_path=config_file, cwd=project_dir)
    except FileNotFoundError:
        console.print("[red]No config found.[/]")
        raise typer.Exit(1)

    sm = StateManager(project_dir / config.project.workspace_dir)
    if not sm.exists():
        console.print("[yellow]No session found.[/]")
        raise typer.Exit()

    state = sm.load()

    if show_decisions and state.decisions:
        table = Table(title="Decision Log", box=box.ROUNDED, border_style="dim")
        table.add_column("ID", width=6)
        table.add_column("Decision")
        table.add_column("Evidence", max_width=40)
        for d in state.decisions:
            table.add_row(d.id, d.decision[:80], d.evidence[:40])
        console.print(table)

    if show_lessons and state.lessons:
        table = Table(title="Lessons Learned", box=box.ROUNDED, border_style="dim")
        table.add_column("Category", width=12)
        table.add_column("Description")
        for l in state.lessons:
            table.add_row(l.category, l.description[:100])
        console.print(table)

    if show_failures and state.failures:
        table = Table(title="Failure History", box=box.ROUNDED, border_style="dim")
        table.add_column("Stage", width=20)
        table.add_column("Classification", width=16)
        table.add_column("Root Cause")
        for f in state.failures:
            table.add_row(f.stage, f.classification.value, f.root_cause[:80])
        console.print(table)


@app.command("providers")
def providers_command(
    config_file: Path = typer.Option(None, "--config", "-c"),
) -> None:
    """List configured providers and test connectivity."""
    from aeos.core.config.loader import load_config
    from aeos.core.providers.router import ModelRouter

    try:
        config = load_config(config_path=config_file)
    except FileNotFoundError:
        console.print("[red]No config found. Run `aeos init`.[/]")
        raise typer.Exit(1)

    router = ModelRouter(config)
    table = Table(title="Provider Connectivity", box=box.ROUNDED)
    table.add_column("Key")
    table.add_column("Type")
    table.add_column("Endpoint")
    table.add_column("Available")

    for key, prov_cfg in config.providers.items():
        provider = router.get_provider(key)
        available = provider.is_available()
        endpoint = prov_cfg.base_url or prov_cfg.project or "cloud"
        table.add_row(
            key,
            prov_cfg.type.value,
            str(endpoint),
            "[green]OK[/]" if available else "[red]FAIL[/]",
        )
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
