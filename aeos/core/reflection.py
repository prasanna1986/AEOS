"""
Reflection engine -- captures lessons learned, patterns, and improvements
after each completed stage or task.
"""

from __future__ import annotations

from datetime import datetime

from aeos.core.providers.router import ModelRouter
from aeos.core.providers.base import Message
from aeos.core.config.schema import TaskType, Complexity
from aeos.core.state.schema import AEOSState, LessonLearned, TaskRecord, TaskStatus
from aeos.core.state.manager import StateManager


class ReflectionEngine:
    """
    After every completed stage or task, reflects on:
    - What changed?
    - What assumptions became invalid?
    - What new evidence was discovered?
    - Should future work change?
    - Are there reusable patterns?
    - Are there common failures to avoid?

    Captured lessons are persisted in state and can be injected into
    future agent prompts to improve execution quality over time.
    """

    def __init__(self, router: ModelRouter, state: AEOSState, sm: StateManager) -> None:
        self._router = router
        self._state = state
        self._sm = sm

    async def reflect_on_task(self, task: TaskRecord) -> list[LessonLearned]:
        """Reflect on a completed or failed task and capture lessons."""
        if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return []

        outcome = "COMPLETED" if task.status == TaskStatus.COMPLETED else "FAILED"
        failures_summary = "\n".join(
            f"- [{f.classification.value}] {f.root_cause}" for f in task.failures
        ) or "None"

        prompt = (
            f"Reflect on the following task execution.\n\n"
            f"**Task**: {task.title}\n"
            f"**Objective**: {task.objective}\n"
            f"**Outcome**: {outcome}\n"
            f"**Retries**: {task.retry_count}\n"
            f"**Failures**:\n{failures_summary}\n"
            f"**Verification passed**: {task.verification_passed}\n\n"
            "Answer these questions concisely:\n"
            "1. What worked well?\n"
            "2. What could be done better?\n"
            "3. Is there a reusable pattern here?\n"
            "4. What assumption was wrong (if failed)?\n"
            "5. Should similar future tasks be approached differently?\n\n"
            "Respond with a JSON array of lessons:\n"
            "[\n"
            "  {\"category\": \"pattern|failure|strategy\", "
            "\"description\": \"...\", \"context\": \"...\"}\n"
            "]"
        )

        messages = [Message(role="user", content=prompt)]
        try:
            response = await self._router.complete(
                messages=messages,
                task_type=TaskType.INFERENCE,
                complexity=Complexity.LOW,
                temperature=0.3,
            )
            import json, re
            match = re.search(r"\[.*\]", response.content, re.DOTALL)
            if match:
                raw_lessons = json.loads(match.group(0))
                lessons = [
                    LessonLearned(
                        category=l.get("category", "pattern"),
                        description=l.get("description", ""),
                        context=l.get("context", task.title),
                    )
                    for l in raw_lessons
                ]
                self._state.lessons.extend(lessons)
                self._sm.save(self._state)
                return lessons
        except Exception:
            pass
        return []

    async def reflect_on_stage(self, stage: str, outcome: str) -> list[LessonLearned]:
        """Reflect on a completed workflow stage."""
        prompt = (
            f"Reflect briefly on the AEOS workflow stage '{stage}' that just completed "
            f"with outcome '{outcome}'.\n\n"
            "What should future executions know?\n"
            "Respond with a JSON array:\n"
            "[{\"category\": \"pattern|failure|strategy\", \"description\": \"...\", \"context\": \"...\"}]"
        )
        messages = [Message(role="user", content=prompt)]
        try:
            response = await self._router.complete(
                messages=messages,
                task_type=TaskType.INFERENCE,
                complexity=Complexity.LOW,
            )
            import json, re
            match = re.search(r"\[.*\]", response.content, re.DOTALL)
            if match:
                raw = json.loads(match.group(0))
                lessons = [
                    LessonLearned(
                        category=l.get("category", "pattern"),
                        description=l.get("description", ""),
                        context=stage,
                    )
                    for l in raw
                ]
                self._state.lessons.extend(lessons)
                self._sm.save(self._state)
                return lessons
        except Exception:
            pass
        return []

    def summarise_lessons(self, category: str | None = None) -> str:
        """Return a formatted summary of captured lessons for prompt injection."""
        lessons = self._state.lessons
        if category:
            lessons = [l for l in lessons if l.category == category]
        if not lessons:
            return ""
        lines = ["## Lessons Learned (from previous execution)"]
        for l in lessons[-20:]:  # cap at 20 most recent
            lines.append(f"- [{l.category}] {l.description}")
        return "\n".join(lines)
