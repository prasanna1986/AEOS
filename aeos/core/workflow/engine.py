"""Workflow engine — drives the full AEOS lifecycle state machine."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from aeos.core.agents.planner import PlannerAgent
from aeos.core.agents.reviewer import ReviewerAgent
from aeos.core.config.schema import AEOSConfig
from aeos.core.providers.router import ModelRouter
from aeos.core.state.manager import StateManager
from aeos.core.state.schema import (
    AEOSState,
    ReviewOutcome,
    TaskRecord,
    TaskStatus,
    DecisionRecord,
)
from aeos.core.tasks.executor import TaskExecutor
from aeos.core.tools.filesystem import list_files, tree, read_file
from aeos.core.tools.shell import run_command
from aeos.core.workflow.stages import (
    WorkflowStage,
    CORE_LIFECYCLE,
    ARTIFACT_STAGE_MAP,
)
from aeos.core.workflow.transitions import get_next_stage

console = Console()


class WorkflowEngine:
    """
    Drives the AEOS lifecycle from INITIALIZE → COMPLETE.

    This is the top-level execution loop. It:
    - Recovers state on startup
    - Executes each lifecycle stage
    - Reviews every artifact before advancing
    - Handles transitions, retries, and replanning
    - Never terminates while executable work remains
    - Stops only to ask the user critical questions
    """

    def __init__(
        self,
        config: AEOSConfig,
        state: AEOSState,
        state_manager: StateManager,
        project_root: Path,
        ask_callback=None,  # callable(question: str) -> str
    ) -> None:
        self._config = config
        self._state = state
        self._sm = state_manager
        self._root = project_root
        self._ask = ask_callback or self._default_ask

        self._router = ModelRouter(config)

        ctx = {
            "objective": state.objective,
            "project_root": str(project_root),
            "current_stage": state.current_stage,
            "discovered_artifacts": state.discovered_artifacts,
            "enabled_tools": state.enabled_tools,
            "decompose_threshold": config.project.decompose_threshold,
        }
        self._planner = PlannerAgent(self._router, ctx)
        self._reviewer = ReviewerAgent(self._router, ctx)
        self._stage_retries: dict[str, int] = {}

    # ─────────────────────────────────────────────────────────
    # Main execution loop
    # ─────────────────────────────────────────────────────────

    async def run(self) -> AEOSState:
        """Execute until COMPLETE or blocked on user input."""
        console.print(
            Panel.fit(
                f"[bold cyan]AEOS[/] — Autonomous Engineering OS\n"
                f"[dim]Objective:[/] {self._state.objective}\n"
                f"[dim]Resuming from:[/] {self._state.current_stage}",
                border_style="cyan",
            )
        )

        while not self._state.is_complete:
            stage = WorkflowStage(self._state.current_stage)
            console.print(f"\n[bold]▶  Stage:[/] {stage.value}")

            try:
                next_stage = await self._execute_stage(stage)
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted — state saved. Run `aeos resume` to continue.[/]")
                break
            except Exception as exc:
                console.print(f"\n[red]Stage error: {exc}[/]")
                next_stage = stage  # stay and retry

            if next_stage == WorkflowStage.COMPLETE:
                self._state.is_complete = True
                self._state.completion_evidence = "All completion criteria verified."
                self._sm.save(self._state)
                console.print("\n[bold green]✓ AEOS — COMPLETE[/]")
                break

            self._sm.update_stage(self._state, next_stage.value)

            # Handle pending critical questions
            if self._state.pending_questions and self._config.project.ask_on_critical:
                await self._handle_questions()

        return self._state

    # ─────────────────────────────────────────────────────────
    # Stage dispatch
    # ─────────────────────────────────────────────────────────

    async def _execute_stage(self, stage: WorkflowStage) -> WorkflowStage:
        match stage:
            case WorkflowStage.INITIALIZE:
                return await self._stage_initialize()
            case WorkflowStage.DISCOVER_CONTEXT:
                return await self._stage_discover_context()
            case WorkflowStage.UNDERSTAND_REQUIREMENTS:
                return await self._stage_understand_requirements()
            case WorkflowStage.REVIEW_REQUIREMENTS:
                return await self._stage_review_requirements()
            case WorkflowStage.PROJECT_PLANNING:
                return await self._stage_project_planning()
            case WorkflowStage.REVIEW_PROJECT_PLAN:
                return await self._stage_review_project_plan()
            case WorkflowStage.PROJECT_DECOMPOSITION:
                return await self._stage_project_decomposition()
            case WorkflowStage.REVIEW_DECOMPOSITION:
                return await self._stage_review_decomposition()
            case WorkflowStage.TASK_QUEUE:
                return await self._stage_task_queue()
            case WorkflowStage.TASK_EXECUTION_ENGINE:
                return await self._stage_task_execution()
            case WorkflowStage.SYSTEM_INTEGRATION:
                return await self._stage_system_integration()
            case WorkflowStage.SYSTEM_REVIEW:
                return await self._stage_system_review()
            case WorkflowStage.FINAL_VERIFICATION:
                return await self._stage_final_verification()
            case WorkflowStage.COMPLETE:
                return WorkflowStage.COMPLETE
            case _:
                # Dynamic stages — treat as pass-through for now
                console.print(f"  [dim]Dynamic stage {stage.value} — passing through[/]")
                return self._next_core_stage(stage)

    # ─────────────────────────────────────────────────────────
    # Individual stage implementations
    # ─────────────────────────────────────────────────────────

    async def _stage_initialize(self) -> WorkflowStage:
        console.print("  Initializing project workspace...")
        aeos_dir = self._root / ".aeos"
        aeos_dir.mkdir(exist_ok=True)
        (aeos_dir / "artifacts").mkdir(exist_ok=True)
        (aeos_dir / "logs").mkdir(exist_ok=True)
        (aeos_dir / "tests").mkdir(exist_ok=True)
        return WorkflowStage.DISCOVER_CONTEXT

    async def _stage_discover_context(self) -> WorkflowStage:
        console.print("  Discovering project context...")
        files = list_files(self._root, exclude=[".git", "__pycache__", ".aeos", "*.pyc", "node_modules"])
        project_tree = tree(self._root, max_depth=3)

        discovered = []
        for f in files[:50]:  # cap at 50
            fname = f.name.lower()
            for keyword, _ in ARTIFACT_STAGE_MAP.items():
                if keyword in fname:
                    discovered.append(str(f.relative_to(self._root)))
                    break

        self._state.discovered_artifacts = discovered
        self._state.context["project_tree"] = project_tree
        self._sm.save(self._state)

        # Activate relevant dynamic stages
        if self._config.project.auto_activate_stages:
            for artifact in discovered:
                for keyword, dyn_stage in ARTIFACT_STAGE_MAP.items():
                    if keyword in artifact.lower():
                        if dyn_stage.value not in self._state.activated_stages:
                            self._state.activated_stages.append(dyn_stage.value)

        console.print(f"  Found {len(files)} files, {len(discovered)} relevant artifacts")
        return WorkflowStage.UNDERSTAND_REQUIREMENTS

    def _resolve_review_outcome(
        self, stage: WorkflowStage, review: dict, default_next: WorkflowStage
    ) -> WorkflowStage:
        """
        Evaluate a review outcome, applying a circuit breaker if the reviewer
        repeatedly requests REVISE/RETRY/REPLAN without reaching PASS.
        """
        outcome = review.get("outcome_enum", ReviewOutcome.PASS)
        summary = review.get("summary", "")
        issues = review.get("issues", [])

        # Store review details in state context
        self._state.context[f"{stage.value}_last_review"] = {
            "outcome": outcome.value,
            "summary": summary,
            "issues": issues,
        }

        if outcome == ReviewOutcome.PASS:
            self._stage_retries[stage.value] = 0
            console.print(f"  {stage.value} review: [bold green]PASS[/] — {summary}")
            return default_next

        # Non-PASS outcome: increment retry count for this stage
        count = self._stage_retries.get(stage.value, 0) + 1
        self._stage_retries[stage.value] = count
        max_retries = max(1, self._config.project.max_retries - 1)

        if count >= max_retries:
            console.print(
                f"  {stage.value} review: [bold yellow]{outcome.value.upper()}[/] (attempt {count}/{max_retries}).\n"
                f"  [bold yellow]⚠ Max revisions reached for {stage.value} — proceeding to next stage with recorded notes.[/]"
            )
            self._state.decisions.append(
                DecisionRecord(
                    decision=f"Proceeding past {stage.value} after {count} revision attempts",
                    evidence=f"Reviewer notes: {summary}. Issues: {issues}",
                )
            )
            self._sm.save(self._state)
            return default_next

        console.print(f"  {stage.value} review: [bold yellow]{outcome.value.upper()}[/] (attempt {count}/{max_retries}) — {summary}")
        return get_next_stage(stage, outcome)

    async def _stage_understand_requirements(self) -> WorkflowStage:
        console.print("  Understanding requirements...")
        last_rev = self._state.context.get(f"{WorkflowStage.REVIEW_REQUIREMENTS.value}_last_review")
        if last_rev and last_rev.get("summary"):
            console.print(f"  [dim]Incorporating review feedback: {last_rev.get('summary')[:80]}[/]")
            self._state.context["requirements_feedback"] = last_rev.get("summary")
        self._state.context["requirements_understood"] = True
        self._sm.save(self._state)
        return WorkflowStage.REVIEW_REQUIREMENTS

    async def _stage_review_requirements(self) -> WorkflowStage:
        req_summary = (
            f"Objective: {self._state.objective}\n"
            f"Discovered artifacts: {self._state.discovered_artifacts}\n"
            f"Context: {json.dumps(self._state.context, default=str, indent=2)[:2000]}"
        )
        review = await self._reviewer.review(req_summary, "requirements", "review_requirements")
        return self._resolve_review_outcome(WorkflowStage.REVIEW_REQUIREMENTS, review, WorkflowStage.PROJECT_PLANNING)

    async def _stage_project_planning(self) -> WorkflowStage:
        console.print("  Generating project plan...")
        context_str = (
            f"Project tree:\n{self._state.context.get('project_tree', '')}\n"
            f"Artifacts: {self._state.discovered_artifacts}\n"
            f"Requirements feedback: {self._state.context.get('requirements_feedback', '')}"
        )
        plan = await self._planner.plan(self._state.objective, context=context_str)
        self._state.context["project_plan"] = plan
        self._sm.save(self._state)
        console.print(f"  Plan: {plan.get('summary', 'Generated')}")
        return WorkflowStage.REVIEW_PROJECT_PLAN

    async def _stage_review_project_plan(self) -> WorkflowStage:
        plan = self._state.context.get("project_plan", {})
        review = await self._reviewer.review(
            json.dumps(plan, indent=2), "plan", "review_project_plan"
        )
        return self._resolve_review_outcome(WorkflowStage.REVIEW_PROJECT_PLAN, review, WorkflowStage.PROJECT_DECOMPOSITION)

    async def _stage_project_decomposition(self) -> WorkflowStage:
        console.print("  Decomposing tasks...")
        plan = self._state.context.get("project_plan", {})
        from uuid import uuid4

        for milestone in plan.get("milestones", []):
            for task_dict in milestone.get("tasks", []):
                task = TaskRecord(
                    id=task_dict.get("id", str(uuid4())[:8]),
                    title=task_dict["title"],
                    description=task_dict.get("description", ""),
                    objective=task_dict.get("objective", ""),
                    complexity=task_dict.get("complexity", "medium"),
                    task_type=task_dict.get("task_type", "coding"),
                    priority=task_dict.get("priority", 50),
                    metadata={
                        "estimated_loc": task_dict.get("estimated_loc", 0),
                        "milestone": milestone.get("title", ""),
                    },
                )
                if task.id not in self._state.tasks:
                    self._state.tasks[task.id] = task
                    self._state.task_queue_order.append(task.id)

        self._sm.save(self._state)
        console.print(f"  {len(self._state.tasks)} tasks queued")
        return WorkflowStage.REVIEW_DECOMPOSITION

    async def _stage_review_decomposition(self) -> WorkflowStage:
        tasks_summary = json.dumps(
            [{"title": t.title, "complexity": t.complexity, "type": t.task_type}
             for t in self._state.tasks.values()],
            indent=2,
        )
        review = await self._reviewer.review(tasks_summary, "plan", "review_decomposition")
        return self._resolve_review_outcome(WorkflowStage.REVIEW_DECOMPOSITION, review, WorkflowStage.TASK_QUEUE)

    async def _stage_task_queue(self) -> WorkflowStage:
        # Sort task queue by priority (descending)
        self._state.task_queue_order.sort(
            key=lambda tid: self._state.tasks.get(tid, TaskRecord(title="")).priority,
            reverse=True,
        )
        self._sm.save(self._state)
        console.print(f"  Task queue ordered: {len(self._state.task_queue_order)} tasks ready")
        return WorkflowStage.TASK_EXECUTION_ENGINE

    async def _stage_task_execution(self) -> WorkflowStage:
        executor = TaskExecutor(
            self._config, self._router, self._state, self._sm, self._root
        )

        pending = [
            tid for tid in self._state.task_queue_order
            if self._state.tasks.get(tid, TaskRecord(title="")).status
            in (TaskStatus.PENDING, TaskStatus.READY)
        ]

        if not pending:
            console.print("  All tasks complete — advancing to integration")
            return WorkflowStage.SYSTEM_INTEGRATION

        for tid in pending:
            task = self._state.tasks[tid]
            if not self._are_dependencies_met(task):
                continue
            self._state.current_task_id = tid
            task = await executor.execute(task)
            self._state.tasks[tid] = task
            self._sm.save(self._state)

        # Check if all tasks done
        all_done = all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for t in self._state.tasks.values()
        )
        return WorkflowStage.SYSTEM_INTEGRATION if all_done else WorkflowStage.TASK_EXECUTION_ENGINE

    async def _stage_system_integration(self) -> WorkflowStage:
        console.print("  Running system integration checks...")
        result = await run_command(
            ["python", "-m", "pytest", "--tb=short", "-q"],
            cwd=self._root,
            timeout=120,
        )
        self._state.verification_results["system_integration"] = result.success
        self._sm.save(self._state)
        console.print(f"  Integration tests: {'PASSED ✓' if result.success else 'FAILED'}")
        return WorkflowStage.SYSTEM_REVIEW

    async def _stage_system_review(self) -> WorkflowStage:
        summary = (
            f"Integration result: {self._state.verification_results.get('system_integration')}\n"
            f"Tasks completed: {sum(1 for t in self._state.tasks.values() if t.status == TaskStatus.COMPLETED)}"
            f" / {len(self._state.tasks)}"
        )
        review = await self._reviewer.review(summary, "implementation", "system_review")
        return self._resolve_review_outcome(WorkflowStage.SYSTEM_REVIEW, review, WorkflowStage.FINAL_VERIFICATION)

    async def _stage_final_verification(self) -> WorkflowStage:
        console.print("  Final verification...")
        checks = {
            "all_tasks_complete": all(
                t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
                for t in self._state.tasks.values()
            ),
            "integration_passed": self._state.verification_results.get("system_integration", False),
            "no_pending_questions": len(self._state.pending_questions) == 0,
        }
        all_passed = all(checks.values())
        self._state.verification_results["final"] = all_passed
        self._sm.save(self._state)

        console.print(f"  Completion checks: {checks}")
        if all_passed:
            return WorkflowStage.COMPLETE
        return WorkflowStage.TASK_EXECUTION_ENGINE

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    def _are_dependencies_met(self, task: TaskRecord) -> bool:
        for dep_id in task.dependencies:
            dep = self._state.tasks.get(dep_id)
            if dep and dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def _next_core_stage(self, current: WorkflowStage) -> WorkflowStage:
        """Return the next stage in the core lifecycle after current."""
        try:
            idx = CORE_LIFECYCLE.index(current)
            return CORE_LIFECYCLE[idx + 1] if idx + 1 < len(CORE_LIFECYCLE) else WorkflowStage.COMPLETE
        except (ValueError, IndexError):
            return WorkflowStage.TASK_EXECUTION_ENGINE

    @staticmethod
    async def _default_ask(question: str) -> str:
        """Default synchronous console ask (used when no callback provided)."""
        return input(f"\n[AEOS] {question}\n> ")

    async def _handle_questions(self) -> None:
        """Present pending critical questions to the user."""
        for q in list(self._state.pending_questions):
            answer = await self._ask(q["question"])
            self._state.decisions.append(
                DecisionRecord(
                    decision=answer,
                    evidence=f"User answered: {answer}",
                    affected_components=[q.get("component", "")],
                )
            )
            self._state.pending_questions.remove(q)
        self._sm.save(self._state)
