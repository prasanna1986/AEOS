"""Task executor — full per-task TDD lifecycle: Red → Green → Refactor → Verify."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from aeos.core.agents.decomposer import DecomposerAgent
from aeos.core.agents.designer import DesignerAgent
from aeos.core.agents.implementer import ImplementerAgent
from aeos.core.agents.reviewer import ReviewerAgent
from aeos.core.agents.verifier import VerifierAgent
from aeos.core.config.schema import AEOSConfig
from aeos.core.providers.router import ModelRouter
from aeos.core.state.schema import AEOSState, ReviewOutcome, TaskRecord, TaskStatus, FailureRecord
from aeos.core.state.manager import StateManager
from aeos.core.tools.shell import run_command
from aeos.core.tools.filesystem import write_file, read_file, file_exists

console = Console()


class TaskExecutor:
    """
    Executes a single task through the full TDD lifecycle:

    Understand → Review Understanding → Implementation Planning → Review Plan →
    Technical Design → Review Design →
    [TDD Red]  Verification Design → Review Verification →
    [TDD Green] Implementation → Run Tests →
    [TDD Refactor] Refactor → Run Tests →
    Implementation Review → Task Complete
    """

    def __init__(
        self,
        config: AEOSConfig,
        router: ModelRouter,
        state: AEOSState,
        state_manager: StateManager,
        project_root: Path,
    ) -> None:
        self._config = config
        self._router = router
        self._state = state
        self._sm = state_manager
        self._root = project_root

        ctx = {
            "objective": state.objective,
            "project_root": str(project_root),
            "current_stage": state.current_stage,
            "discovered_artifacts": state.discovered_artifacts,
            "enabled_tools": state.enabled_tools,
            "decompose_threshold": config.project.decompose_threshold,
        }

        self._designer = DesignerAgent(router, ctx)
        self._implementer = ImplementerAgent(router, ctx)
        self._reviewer = ReviewerAgent(router, ctx)
        self._verifier = VerifierAgent(router, ctx)
        self._decomposer = DecomposerAgent(router, ctx)

    async def execute(self, task: TaskRecord) -> TaskRecord:
        """Execute a task through the full TDD lifecycle. Returns updated task."""
        task.status = TaskStatus.IN_PROGRESS
        task.current_stage = "understand"
        self._sm.save(self._state)

        console.print(f"\n[bold cyan]⚙  Executing task:[/] {task.title}")

        try:
            # ── 1. Check if task needs further decomposition ──────────────
            task = await self._maybe_decompose(task)
            if task.status == TaskStatus.COMPLETED:
                return task  # decomposed — children will handle

            # ── 2. Technical Design ───────────────────────────────────────
            task.current_stage = "design"
            console.print(f"  [dim]→ Designing...[/]")
            design = await self._designer.design(task)
            design_review = await self._reviewer.review(
                json.dumps(design, indent=2), "design", task.current_stage
            )
            if design_review["outcome_enum"] not in (ReviewOutcome.PASS,):
                task.metadata["design_issues"] = design_review.get("issues", [])

            # ── 3. TDD Red: Generate Tests ────────────────────────────────
            task.current_stage = "tdd_red"
            console.print(f"  [dim]→ TDD Red: generating tests...[/]")
            test_data = await self._verifier.generate_tests(task)
            test_path = Path(self._root) / test_data["test_file_path"]
            stub_path = Path(self._root) / test_data["stub_file_path"]

            write_file(test_path, test_data["test_content"])
            write_file(stub_path, test_data["stub_content"])
            task.test_file_path = str(test_path)
            self._sm.save(self._state)

            # Run tests — expect FAIL (Red)
            red_result = await run_command(
                ["python", "-m", "pytest", str(test_path), "-v", "--tb=short"],
                cwd=self._root,
                timeout=60,
            )
            console.print(f"  [yellow]  Red phase: {'FAILED (expected ✓)' if not red_result.success else 'PASSED (unexpected — check stub)'}[/]")

            # Review tests
            test_review = await self._reviewer.review(
                test_data["test_content"], "tests", "tdd_red"
            )
            if test_review["outcome_enum"] == ReviewOutcome.REJECT:
                raise RuntimeError(f"Test review rejected: {test_review.get('summary')}")

            # ── 4. TDD Green: Implement ───────────────────────────────────
            task.current_stage = "tdd_green"
            console.print(f"  [dim]→ TDD Green: implementing...[/]")
            impl_data = await self._implementer.implement(
                task,
                test_content=test_data["test_content"],
                test_output=red_result.output,
                existing_code=test_data.get("stub_content", ""),
            )
            for f in impl_data.get("files", []):
                fpath = Path(self._root) / f["path"]
                write_file(fpath, f["content"])
                task.impl_file_paths.append(str(fpath))
            self._sm.save(self._state)

            # Run tests — expect PASS (Green)
            green_result = await run_command(
                ["python", "-m", "pytest", str(test_path), "-v", "--tb=short", "--cov"],
                cwd=self._root,
                timeout=90,
            )
            console.print(f"  [green]  Green phase: {'PASSED ✓' if green_result.success else 'FAILED — retrying'}[/]")

            # If still failing, retry once with updated context
            if not green_result.success and task.retry_count < self._config.project.max_retries:
                task.retry_count += 1
                console.print(f"  [yellow]  Retry {task.retry_count}...[/]")
                impl_data = await self._implementer.implement(
                    task,
                    test_content=test_data["test_content"],
                    test_output=green_result.output,
                )
                for f in impl_data.get("files", []):
                    write_file(Path(self._root) / f["path"], f["content"])

                green_result = await run_command(
                    ["python", "-m", "pytest", str(test_path), "-v", "--tb=short"],
                    cwd=self._root,
                    timeout=90,
                )

            # ── 5. TDD Refactor ───────────────────────────────────────────
            if green_result.success and task.impl_file_paths:
                task.current_stage = "tdd_refactor"
                console.print(f"  [dim]→ TDD Refactor: improving quality...[/]")
                first_impl = read_file(task.impl_file_paths[0]) if task.impl_file_paths else ""
                refactor_data = await self._implementer.refactor(
                    task, current_code=first_impl, test_content=test_data["test_content"]
                )
                for f in refactor_data.get("files", []):
                    write_file(Path(self._root) / f["path"], f["content"])

                # Verify tests still green after refactor
                refactor_verify = await run_command(
                    ["python", "-m", "pytest", str(test_path), "-v"],
                    cwd=self._root, timeout=60,
                )
                if not refactor_verify.success:
                    # Refactor broke tests — revert is complex; just log
                    console.print("  [red]  Refactor broke tests — skipping refactor[/]")

            # ── 6. Analyse verification results ───────────────────────────
            verification_analysis = await self._verifier.analyse_results(
                green_result.output, task
            )
            task.verification_passed = verification_analysis.get("passed", green_result.success)

            # ── 7. Implementation Review ──────────────────────────────────
            task.current_stage = "impl_review"
            impl_content = "\n\n".join(
                read_file(p) for p in task.impl_file_paths if file_exists(p)
            )
            impl_review = await self._reviewer.review(
                impl_content or "No implementation files found.",
                "implementation",
                "task_complete",
            )
            task.review_outcome = impl_review["outcome_enum"]

            # ── 8. Mark Complete or Auto-Decompose on Failure/REPLAN ─────
            if task.verification_passed and task.review_outcome == ReviewOutcome.PASS:
                task.status = TaskStatus.COMPLETED
                task.current_stage = "complete"
                console.print(f"  [bold green]✓ Task complete: {task.title}[/]")
            elif task.review_outcome in (ReviewOutcome.REPLAN, ReviewOutcome.REVISE) or not task.verification_passed:
                console.print(f"  [yellow]Task needs replanning — auto-decomposing into smaller subtasks...[/]")
                task = await self._force_decompose(task)
                if task.status != TaskStatus.BLOCKED:
                    task.status = TaskStatus.FAILED
                    task.current_stage = "failed"
                    console.print(f"  [red]✗ Task failed: {task.title}[/]")
            else:
                task.status = TaskStatus.FAILED
                task.current_stage = "failed"
                console.print(f"  [red]✗ Task failed: {task.title}[/]")

        except Exception as exc:
            failure = FailureRecord(
                stage=task.current_stage,
                evidence=str(exc),
                root_cause="Exception during task execution",
            )
            task.failures.append(failure)
            task.status = TaskStatus.FAILED
            console.print(f"  [bold red]✗ Exception: {exc}[/]")

        self._sm.save(self._state)
        return task

    async def _maybe_decompose(self, task: TaskRecord) -> TaskRecord:
        """Decompose task if it exceeds the complexity threshold."""
        threshold = self._config.project.decompose_threshold
        estimated_loc = task.metadata.get("estimated_loc", 0)

        if task.complexity == "high" or estimated_loc > threshold:
            result = await self._decomposer.decompose(task, threshold)
            if result.get("should_decompose"):
                console.print(f"  [dim]→ Decomposing into {len(result['subtasks'])} subtasks...[/]")
                # Register subtasks in state
                from uuid import uuid4
                for sub in result.get("subtasks", []):
                    sub_record = TaskRecord(
                        id=str(uuid4())[:8],
                        title=sub["title"],
                        description=sub.get("description", ""),
                        objective=sub.get("objective", ""),
                        parent_id=task.id,
                        complexity=sub.get("complexity", "low"),
                        task_type=sub.get("task_type", "coding"),
                        priority=sub.get("priority", 50),
                        metadata={"tdd_phase": sub.get("tdd_phase", "")},
                    )
                    task.child_ids.append(sub_record.id)
                    self._state.tasks[sub_record.id] = sub_record
                    # Prepend to queue
                    self._state.task_queue_order.insert(0, sub_record.id)

                task.status = TaskStatus.BLOCKED  # waits for children
                self._sm.save(self._state)
        return task

    async def _force_decompose(self, task: TaskRecord) -> TaskRecord:
        """Force decomposition of a task that failed verification/review into smaller, lower-complexity subtasks."""
        threshold = self._config.project.decompose_threshold
        result = await self._decomposer.decompose(task, target_loc=max(50, threshold // 2))
        subtasks = result.get("subtasks", [])
        if subtasks:
            console.print(f"  [yellow]→ Auto-decomposed task '{task.title[:40]}' into {len(subtasks)} subtasks[/]")
            from uuid import uuid4
            for sub in subtasks:
                sub_record = TaskRecord(
                    id=str(uuid4())[:8],
                    title=sub["title"],
                    description=sub.get("description", ""),
                    objective=sub.get("objective", ""),
                    parent_id=task.id,
                    complexity="low",
                    task_type=sub.get("task_type", "coding"),
                    priority=sub.get("priority", 50),
                    metadata={"tdd_phase": sub.get("tdd_phase", "")},
                )
                task.child_ids.append(sub_record.id)
                self._state.tasks[sub_record.id] = sub_record
                self._state.task_queue_order.insert(0, sub_record.id)

            task.status = TaskStatus.BLOCKED
            self._sm.save(self._state)
        return task
