"""
aeos run -- start or resume autonomous engineering execution.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from aeos.core.config.loader import load_config
from aeos.core.state.manager import StateManager
from aeos.core.workflow.engine import WorkflowEngine

console = Console()


def run_command(
    objective: str = typer.Argument(..., help="Engineering objective to achieve"),
    project_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Project root directory"),
    config_file: Path = typer.Option(None, "--config", "-c", help="Path to AEOS config file"),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume previous session"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """
    Run AEOS autonomously until the objective is achieved.

    AEOS will plan, decompose, implement with TDD, verify, and integrate
    continuously until all completion criteria are met. It only stops
    to ask critical questions.
    """
    console.print(
        Panel.fit(
            f"[bold cyan]AEOS[/] -- Autonomous Engineering OS\n"
            f"[dim]Objective:[/] {objective}",
            border_style="cyan",
        )
    )

    # Load config
    try:
        config = load_config(config_path=config_file, cwd=project_dir)
    except FileNotFoundError:
        console.print(
            "[red]No AEOS config found.[/]\n"
            "Run [bold]aeos init[/] to create one.\n"
            "Or copy [dim]config.example.yaml[/] to [dim]~/.aeos/config.yaml[/]"
        )
        raise typer.Exit(1)

    workspace = project_dir / config.project.workspace_dir
    sm = StateManager(workspace)

    # Determine: resume or fresh start
    if sm.exists() and not resume:
        existing = sm.load()
        if not yes:
            console.print(
                f"[yellow]Existing session found:[/] stage={existing.current_stage}, "
                f"tasks={len(existing.tasks)}"
            )
            do_resume = Confirm.ask("Resume this session?", default=True)
        else:
            do_resume = False

        if do_resume:
            state = existing
            console.print(f"[green]Resuming from:[/] {state.current_stage}")
        else:
            state = sm.reset(objective=objective, project_root=str(project_dir))
    elif sm.exists() and resume:
        state = sm.load()
        console.print(f"[green]Resuming from:[/] {state.current_stage}")
    else:
        state = sm.reset(objective=objective, project_root=str(project_dir))
        console.print("[green]Starting fresh session[/]")

    # Build and run workflow engine
    engine = WorkflowEngine(
        config=config,
        state=state,
        state_manager=sm,
        project_root=project_dir.resolve(),
        ask_callback=_console_ask,
    )

    asyncio.run(engine.run())


async def _console_ask(question: str) -> str:
    """Present a critical question to the user and return their answer."""
    console.print(f"\n[bold yellow]!  Critical question:[/]\n{question}")
    return typer.prompt("Your answer")
