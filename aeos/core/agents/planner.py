"""Planner agent -- generates project plans from objectives."""

from __future__ import annotations

from aeos.core.agents.base import BaseAgent
from aeos.core.config.schema import Complexity, TaskType


class PlannerAgent(BaseAgent):
    task_type = TaskType.PLANNING
    complexity = Complexity.HIGH

    async def plan(self, objective: str, context: str = "") -> dict:
        """
        Generate a structured project plan for the given objective.

        Returns a dict with: summary, milestones, tasks, risks, dynamic_stages.
        """
        user_prompt = self._render(
            "planner.j2",
            objective=objective,
            context=context,
        )
        response = await self._call(user_prompt)
        return self.extract_json(response)
