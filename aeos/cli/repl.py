"""
AEOS Interactive REPL — Claude-style persistent interactive shell.

Enter `aeos` (no arguments) to start the interactive session.
Type your engineering objective and AEOS runs autonomously.
AEOS pauses only for critical questions. Type slash commands anytime.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich import box

from aeos.core.config.loader import load_config
from aeos.core.config.schema import AEOSConfig
from aeos.core.state.manager import StateManager
from aeos.core.state.schema import AEOSState, TaskStatus
from aeos.core.workflow.engine import WorkflowEngine

console = Console()

# ── REPL Theme ───────────────────────────────────────────────
REPL_STYLE = Style.from_dict({
    "prompt":       "#00d7ff bold",
    "prompt.arrow": "#005f87",
    "status":       "#87ff87 italic",
    "command":      "#ffaf00",
    "dim":          "#626262",
})

BANNER = """
[bold cyan]  ╔═══════════════════════════════════════════╗[/]
[bold cyan]  ║  [white]AEOS[/] [dim]Autonomous Engineering OS[/]          [bold cyan]║[/]
[bold cyan]  ╚═══════════════════════════════════════════╝[/]
  [dim]Type your objective and press Enter to begin.[/]
  [dim]Type[/] [yellow]/help[/] [dim]for commands,[/] [yellow]/quit[/] [dim]to exit.[/]
"""

HELP_TEXT = """
[bold cyan]AEOS Interactive Commands[/]

  [yellow]/status[/]        Show current workflow stage and task progress
  [yellow]/log[/]           Show decision log, lessons, and failure history
  [yellow]/providers[/]     Test connectivity to all configured providers
  [yellow]/config[/]        Show resolved configuration and routing table
  [yellow]/reset[/]         Archive current session and start fresh
  [yellow]/resume[/]        Resume the previous session from interruption point
  [yellow]/quit[/] [dim]/ /q[/]    Exit AEOS
  [yellow]/help[/]          Show this help

[bold]To run:[/] Just type your engineering objective and press [bold]Enter[/].
  [dim]Example:[/] Build a FastAPI REST service with JWT authentication
  [dim]Example:[/] Add comprehensive unit tests to the existing Python library
  [dim]Example:[/] Refactor the database layer to use async SQLAlchemy
"""

SLASH_COMMANDS = {"/help", "/status", "/log", "/providers", "/config", "/reset", "/resume", "/quit", "/q"}


class AEOSRepl:
    """
    Interactive REPL shell for AEOS.

    Maintains a persistent session across multiple objectives.
    Streams execution output in real-time.
    Pauses for critical questions inline.
    """

    def __init__(self, project_dir: Path, config_file: Path | None = None) -> None:
        self._project_dir = project_dir.resolve()
        self._config_file = config_file
        self._config: AEOSConfig | None = None
        self._state: AEOSState | None = None
        self._sm: StateManager | None = None
        self._running_task: asyncio.Task | None = None

        # History file for up-arrow recall
        history_dir = Path.home() / ".aeos"
        history_dir.mkdir(exist_ok=True)
        self._history = FileHistory(str(history_dir / "repl_history"))

    # ── Bootstrap ────────────────────────────────────────────

    def _load_config(self) -> bool:
        """Load config; return False if not found."""
        try:
            self._config = load_config(config_path=self._config_file, cwd=self._project_dir)
            return True
        except FileNotFoundError:
            console.print(
                "\n[red]No AEOS config found.[/]\n"
                "Run [bold yellow]/init[/] or create [cyan]~/.aeos/config.yaml[/] first.\n"
                "Copy [dim]config.example.yaml[/] from the AEOS repo as a starting point.\n"
            )
            return False

    def _load_state(self) -> None:
        if self._config is None:
            return
        workspace = self._project_dir / self._config.project.workspace_dir
        self._sm = StateManager(workspace)
        if self._sm.exists():
            self._state = self._sm.load()

    # ── Main entry point ────────────────────────────────────

    def run(self) -> None:
        """Start the REPL. Blocks until the user quits."""
        console.print(BANNER)

        if not self._load_config():
            console.print("[dim]Continuing without config — only /help commands available.[/]\n")
        else:
            self._load_state()
            self._print_session_info()

        session: PromptSession = PromptSession(
            history=self._history,
            auto_suggest=AutoSuggestFromHistory(),
            style=REPL_STYLE,
            multiline=False,
            enable_history_search=True,
        )

        while True:
            try:
                stage = self._state.current_stage if self._state else "no session"
                prompt_html = HTML(
                    f'<prompt>aeos</prompt>'
                    f'<dim> [{stage}]</dim>'
                    f'<prompt.arrow> ❯ </prompt.arrow>'
                )
                raw = session.prompt(prompt_html).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Use[/] [yellow]/quit[/] [dim]to exit.[/]")
                continue

            if not raw:
                continue

            if raw.lower() in ("/quit", "/q", "quit", "exit"):
                console.print("[dim]Goodbye. State saved — run[/] [bold]aeos[/] [dim]to resume.[/]")
                break

            if raw.startswith("/"):
                self._handle_slash_command(raw)
            else:
                # Treat as an engineering objective
                asyncio.run(self._run_objective(raw))

    # ── Slash commands ───────────────────────────────────────

    def _handle_slash_command(self, cmd: str) -> None:
        cmd_lower = cmd.lower().split()[0]
        match cmd_lower:
            case "/help":
                console.print(Panel(HELP_TEXT, border_style="dim", expand=False))
            case "/status":
                self._print_status()
            case "/log":
                self._print_log()
            case "/providers":
                self._print_providers()
            case "/config":
                self._print_config()
            case "/reset":
                self._reset_session()
            case "/resume":
                asyncio.run(self._resume_session())
            case _:
                console.print(f"[red]Unknown command:[/] {cmd}  (type [yellow]/help[/] for commands)")

    # ── Objective execution ──────────────────────────────────

    async def _run_objective(self, objective: str) -> None:
        """Run AEOS for a given objective, streaming output in real-time."""
        if self._config is None:
            console.print("[red]No config loaded. Cannot run.[/]")
            return

        console.print(Rule(f"[bold cyan]Starting:[/] {objective[:80]}", style="cyan"))

        # Fresh or resume?
        if self._state and not self._state.is_complete:
            same_obj = self._state.objective == objective
            if same_obj:
                console.print(
                    f"[yellow]Active session found[/] (stage: {self._state.current_stage}). "
                    f"[dim]Resuming...[/]"
                )
            else:
                console.print(
                    f"[yellow]Active session has a different objective:[/] "
                    f"[dim]{self._state.objective[:60]}[/]\n"
                    f"Starting new session for: [cyan]{objective[:60]}[/]"
                )
                self._state = self._sm.reset(objective=objective, project_root=str(self._project_dir))
        else:
            self._state = self._sm.reset(objective=objective, project_root=str(self._project_dir))

        engine = WorkflowEngine(
            config=self._config,
            state=self._state,
            state_manager=self._sm,
            project_root=self._project_dir,
            ask_callback=self._ask_user,  # <- inline Q&A
        )

        try:
            self._state = await engine.run()
        except KeyboardInterrupt:
            console.print(
                "\n[yellow]⚠ Interrupted.[/] State saved.\n"
                "Type [yellow]/resume[/] to continue from here."
            )
        except Exception as exc:
            console.print(f"\n[red]Execution error:[/] {exc}")
            console.print("[dim]State saved. Type[/] [yellow]/resume[/] [dim]to retry.[/]")

        if self._state and self._state.is_complete:
            console.print(
                Panel.fit(
                    "[bold green]✓ Objective Complete[/]\n"
                    f"[dim]{self._state.completion_evidence or 'All verification criteria met.'}[/]",
                    border_style="green",
                )
            )
        console.print()

    async def _resume_session(self) -> None:
        """Resume the current session from its saved stage."""
        if self._config is None:
            console.print("[red]No config loaded.[/]")
            return
        if self._sm is None or not self._sm.exists():
            console.print("[yellow]No session to resume.[/]")
            return
        self._state = self._sm.load()
        console.print(f"[green]Resuming from:[/] {self._state.current_stage}")
        await self._run_objective(self._state.objective)

    # ── Inline Q&A callback ──────────────────────────────────

    async def _ask_user(self, question: str) -> str:
        """
        Called by WorkflowEngine when a critical question needs user input.
        Renders the question inline in the REPL and waits for an answer.
        """
        console.print()
        console.print(
            Panel(
                f"[bold yellow]⚠ Critical Question[/]\n\n{question}",
                border_style="yellow",
                expand=False,
            )
        )
        # Run the blocking prompt in a thread to not block the event loop
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            None,
            lambda: input("  Your answer: ").strip()
        )
        console.print(f"  [dim]→ Recorded: {answer[:80]}[/]\n")
        return answer

    # ── Display helpers ──────────────────────────────────────

    def _print_session_info(self) -> None:
        if self._state is None:
            console.print("[dim]No active session — type your objective to begin.[/]\n")
            return
        status = "[green]COMPLETE[/]" if self._state.is_complete else "[yellow]IN PROGRESS[/]"
        console.print(
            f"[dim]Session:[/] {self._state.session_id}  "
            f"[dim]Stage:[/] {self._state.current_stage}  "
            f"[dim]Status:[/] {status}\n"
            f"[dim]Objective:[/] {self._state.objective[:100]}\n"
        )

    def _print_status(self) -> None:
        if self._state is None:
            console.print("[yellow]No active session.[/]")
            return

        console.print(
            Panel.fit(
                f"[bold]Session:[/] {self._state.session_id}\n"
                f"[bold]Objective:[/] {self._state.objective}\n"
                f"[bold]Stage:[/] [cyan]{self._state.current_stage}[/]\n"
                f"[bold]Complete:[/] {'[green]YES[/]' if self._state.is_complete else '[yellow]NO[/]'}",
                title="[bold cyan]Status[/]",
                border_style="cyan",
            )
        )

        if self._state.tasks:
            table = Table(box=box.SIMPLE, border_style="dim", show_header=True)
            table.add_column("Title", max_width=50)
            table.add_column("Status", width=14)
            table.add_column("✓", width=3)

            status_icons = {
                TaskStatus.COMPLETED:   "[green]✓ done[/]",
                TaskStatus.IN_PROGRESS: "[cyan]⚙ running[/]",
                TaskStatus.FAILED:      "[red]✗ failed[/]",
                TaskStatus.BLOCKED:     "[yellow]⏸ blocked[/]",
                TaskStatus.PENDING:     "[dim]◦ pending[/]",
                TaskStatus.READY:       "[blue]● ready[/]",
                TaskStatus.SKIPPED:     "[dim]— skipped[/]",
            }

            for task in list(self._state.tasks.values())[:20]:
                table.add_row(
                    task.title[:48],
                    status_icons.get(task.status, task.status.value),
                    "[green]✓[/]" if task.verification_passed else "[dim]—[/]",
                )
            console.print(table)

    def _print_log(self) -> None:
        if self._state is None:
            console.print("[yellow]No session.[/]")
            return

        if self._state.decisions:
            table = Table(title="Decisions", box=box.SIMPLE)
            table.add_column("Decision")
            table.add_column("Evidence", max_width=50)
            for d in self._state.decisions[-10:]:
                table.add_row(d.decision[:80], d.evidence[:50])
            console.print(table)

        if self._state.lessons:
            table = Table(title="Lessons Learned", box=box.SIMPLE)
            table.add_column("Category", width=12)
            table.add_column("Description")
            for l in self._state.lessons[-10:]:
                table.add_row(l.category, l.description[:100])
            console.print(table)

        if self._state.failures:
            table = Table(title="Failures", box=box.SIMPLE)
            table.add_column("Stage")
            table.add_column("Classification")
            table.add_column("Root Cause")
            for f in self._state.failures[-10:]:
                table.add_row(f.stage, f.classification.value, f.root_cause[:80])
            console.print(table)

    def _print_providers(self) -> None:
        if self._config is None:
            console.print("[yellow]No config loaded.[/]")
            return
        from aeos.core.providers.router import ModelRouter
        router = ModelRouter(self._config)
        table = Table(title="Provider Connectivity", box=box.SIMPLE)
        table.add_column("Key")
        table.add_column("Type")
        table.add_column("Endpoint")
        table.add_column("Online")
        for key, prov in self._config.providers.items():
            provider = router.get_provider(key)
            available = provider.is_available()
            endpoint = str(prov.base_url or prov.project or "cloud")
            table.add_row(
                key, prov.type.value, endpoint[:40],
                "[green]✓[/]" if available else "[red]✗[/]",
            )
        console.print(table)

    def _print_config(self) -> None:
        if self._config is None:
            console.print("[yellow]No config loaded.[/]")
            return
        routing = self._config.routing.describe_routing()
        table = Table(title="Model Routing", box=box.SIMPLE)
        table.add_column("Task Type", width=14)
        table.add_column("High")
        table.add_column("Medium")
        table.add_column("Low")
        for tt, cmap in routing.items():
            table.add_row(tt, cmap.get("high","—"), cmap.get("medium","—"), cmap.get("low","—"))
        console.print(table)

    def _reset_session(self) -> None:
        if self._sm is None:
            console.print("[yellow]No session manager.[/]")
            return
        confirm = input("  Archive current session and start fresh? [y/N]: ").strip().lower()
        if confirm == "y":
            self._state = None
            console.print("[green]Session archived.[/] Type your next objective to begin.")
        else:
            console.print("[dim]Reset cancelled.[/]")
