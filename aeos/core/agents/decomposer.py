"""Decomposer agent -- recursively breaks tasks into atomic units with TDD ordering."""

from __future__ import annotations

from aeos.core.agents.base import BaseAgent
from aeos.core.config.schema import Complexity, TaskType
from aeos.core.state.schema import TaskRecord


class DecomposerAgent(BaseAgent):
    task_type = TaskType.PLANNING
    complexity = Complexity.MEDIUM

    async def decompose(self, task: TaskRecord, decompose_threshold: int = 300) -> dict:
        """
        Determine if a task should be decomposed and produce subtasks.

        Returns dict with: should_decompose (bool), reason, subtasks (list).
        """
        task_dict = {
            "title": task.title,
            "description": task.description,
            "objective": task.objective,
            "complexity": task.complexity,
            "estimated_loc": task.metadata.get("estimated_loc", "unknown"),
        }
        user_prompt = self._render(
            "decomposer.j2",
            task=task_dict,
            decompose_threshold=decompose_threshold,
        )
        response = await self._call(user_prompt)
        return self.extract_json(response)
