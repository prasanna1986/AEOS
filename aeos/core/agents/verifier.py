"""Verifier agent -- generates tests (TDD Red) and analyses verification results."""

from __future__ import annotations

from aeos.core.agents.base import BaseAgent
from aeos.core.config.schema import Complexity, TaskType
from aeos.core.state.schema import TaskRecord


class VerifierAgent(BaseAgent):
    task_type = TaskType.VERIFICATION
    complexity = Complexity.LOW   # SLMs handle focused test generation well

    async def generate_tests(
        self,
        task: TaskRecord,
        existing_code: str = "",
        language: str = "Python",
        test_framework: str = "pytest",
    ) -> dict:
        """
        TDD Red Phase: generate failing tests that define the task contract.

        Returns dict with: test_file_path, test_content, stub_file_path, stub_content.
        """
        user_prompt = self._render(
            "verifier.j2",
            task={"title": task.title, "objective": task.objective, "description": task.description},
            existing_code=existing_code,
            language=language,
            test_framework=test_framework,
        )
        response = await self._call(user_prompt, complexity=Complexity.LOW)
        return self.extract_json(response)

    async def analyse_results(self, test_output: str, task: TaskRecord) -> dict:
        """
        Analyse test run output and determine if verification passed.

        Returns dict with: passed (bool), failures (list), coverage (float), summary.
        """
        prompt = (
            f"Analyse the following test output for task '{task.title}'.\n"
            f"Determine: did all tests pass? What failed? What is the coverage?\n\n"
            f"```\n{test_output}\n```\n\n"
            "Respond with JSON: {\"passed\": bool, \"failures\": [], \"coverage\": 0.0, \"summary\": \"\"}"
        )
        response = await self._call(prompt, complexity=Complexity.LOW)
        return self.extract_json(response)
