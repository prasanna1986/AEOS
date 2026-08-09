"""Implementer agent -- TDD Green phase: minimum code to pass failing tests."""

from __future__ import annotations

from aeos.core.agents.base import BaseAgent
from aeos.core.config.schema import Complexity, TaskType
from aeos.core.state.schema import TaskRecord


class ImplementerAgent(BaseAgent):
    task_type = TaskType.CODING
    complexity = Complexity.LOW   # Atomic tasks are SLM-suitable

    async def implement(
        self,
        task: TaskRecord,
        test_content: str,
        test_output: str,
        existing_code: str = "",
        coding_style: str = "PEP 8, type hints required",
    ) -> dict:
        """
        TDD Green Phase: write minimum code to make failing tests pass.

        Returns dict with: files (list of {path, content}), explanation, known_limitations.
        """
        # Use medium complexity if the task is marked high
        complexity = (
            Complexity.MEDIUM if task.complexity == "high" else Complexity.LOW
        )
        user_prompt = self._render(
            "implementer.j2",
            task={"title": task.title, "objective": task.objective},
            test_content=test_content,
            test_output=test_output,
            existing_code=existing_code,
            coding_style=coding_style,
        )
        response = await self._call(user_prompt, complexity=complexity)
        return self.extract_json(response)

    async def refactor(
        self,
        task: TaskRecord,
        current_code: str,
        test_content: str,
    ) -> dict:
        """
        TDD Refactor Phase: improve code quality while keeping tests green.

        Returns dict with: files (list of {path, content}), changes_made.
        """
        prompt = (
            f"Refactor the following code for task '{task.title}'.\n"
            f"Rules: tests must remain green, improve readability/maintainability only.\n\n"
            f"### Current Code\n```python\n{current_code}\n```\n\n"
            f"### Tests (must stay green)\n```python\n{test_content}\n```\n\n"
            "Respond with JSON: {\"files\": [{\"path\": \"...\", \"content\": \"...\"}], \"changes_made\": \"...\"}"
        )
        response = await self._call(prompt, complexity=Complexity.LOW)
        return self.extract_json(response)
