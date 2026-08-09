"""aeos status — display current workflow state and task queue."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from aeos.core.config.loader import load_config
from aeos.core.state.manager import StateManager
from aeos.core.state.schema import TaskStatus

console = Console()


def status_command(
    project_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Project directory"),
) -> None:
    """Show current AEOS workflow stage, task queue, and progress."""
    try:
        config = load_config(cwd=project_dir)
    except FileNotFoundError:
        console.print("[red]No AEOS config found. Run `aeos init` first.[/]")
        raise typer.Exit(1)

    workspace = project_dir / config.project.workspace_dir
    sm = StateManager(workspace)

    if not sm.exists():
        console.print("[yellow]No active AEOS session found in this directory.[/]")
        console.print("  Start one with: [bold]aeos run \"<objective>\"[/]")
        raise typer.Exit()

    state = sm.load()

    # ── Overview ─────────────────────────────────────────────
    status_color = "green" if state.is_complete else "cyan"
    console.print(
        Panel.fit(
            f"[bold]Session:[/] {state.session_id}\n"
            f"[bold]Objective:[/] {state.objective}\n"
            f"[bold]Stage:[/] [{status_color}]{state.current_stage}[/{status_color}]\n"
            f"[bold]Status:[/] {'[green]COMPLETE[/]' if state.is_complete else '[yellow]IN PROGRESS[/]'}",
            title="[bold cyan]AEOS Status[/]",
            border_style="cyan",
        )
    )

    # ── Task Table ────────────────────────────────────────────
    if state.tasks:
        table = Table(title="Task Queue", box=box.ROUNDED, border_style="dim")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Title", max_width=50)
        table.add_column("Type", width=12)
        table.add_column("Complexity", width=10)
        table.add_column("Status", width=14)
        table.add_column("Verified", width=8)

        status_styles = {
            TaskStatus.COMPLETED: "[green]✓ complete[/]",
            TaskStatus.IN_PROGRESS: "[cyan]⚙ running[/]",
            TaskStatus.FAILED: "[red]✗ failed[/]",
            TaskStatus.BLOCKED: "[yellow]⏸ blocked[/]",
            TaskStatus.PENDING: "[dim]◦ pending[/]",
            TaskStatus.READY: "[blue]● ready[/]",
            TaskStatus.SKIPPED: "[dim]— skipped[/]",
        }

        for task in state.tasks.values():
            table.add_row(
                task.id,
                task.title[:48] + ("…" if len(task.title) > 48 else ""),
                task.task_type,
                task.complexity,
                status_styles.get(task.status, task.status.value),
                "[green]✓[/]" if task.verification_passed else "[dim]—[/]",
            )
        console.print(table)

    # ── Decisions ────────────────────────────────────────────
    if state.decisions:
        console.print(f"\n[dim]{len(state.decisions)} decisions recorded.[/]")

    # ── Failures ─────────────────────────────────────────────
    failed_tasks = [t for t in state.tasks.values() if t.status == TaskStatus.FAILED]
    if failed_tasks:
        console.print(f"\n[red]{len(failed_tasks)} tasks failed:[/]")
        for t in failed_tasks:
            console.print(f"  • {t.title} (retries: {t.retry_count})")
