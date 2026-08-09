"""Designer agent — technical design documents and architecture."""

from __future__ import annotations

from aeos.core.agents.base import BaseAgent
from aeos.core.config.schema import Complexity, TaskType
from aeos.core.state.schema import TaskRecord


class DesignerAgent(BaseAgent):
    task_type = TaskType.CODING
    complexity = Complexity.HIGH

    async def design(self, task: TaskRecord, context: str = "") -> dict:
        """
        Produce a technical design for a task.

        Returns dict with: design_doc, interfaces, data_models, error_handling, test_strategy.
        """
        prompt = (
            f"Produce a technical design for the following engineering task.\n\n"
            f"**Task**: {task.title}\n"
            f"**Objective**: {task.objective}\n"
            f"**Description**: {task.description}\n\n"
            f"**Context**:\n{context}\n\n"
            "Output JSON:\n"
            "{\n"
            '  "design_doc": "markdown formatted design document",\n'
            '  "interfaces": [{"name": "...", "signature": "...", "purpose": "..."}],\n'
            '  "data_models": [{"name": "...", "fields": []}],\n'
            '  "error_handling": "how errors are handled",\n'
            '  "test_strategy": "what needs to be tested and how",\n'
            '  "file_structure": ["list of files to create/modify"]\n'
            "}"
        )
        response = await self._call(prompt)
        return self.extract_json(response)
