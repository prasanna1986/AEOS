"""Reviewer agent -- evidence-based artifact review with structured outcomes."""

from __future__ import annotations

from aeos.core.agents.base import BaseAgent
from aeos.core.config.schema import Complexity, TaskType
from aeos.core.state.schema import ReviewOutcome


class ReviewerAgent(BaseAgent):
    task_type = TaskType.REVIEW
    complexity = Complexity.MEDIUM  # MEDIUM keeps token budget safe for local models

    async def review(
        self,
        artifact_content: str,
        artifact_type: str,
        stage: str,
        context: str = "",
    ) -> dict:
        """
        Review an artifact and return a structured verdict.

        Returns dict with: outcome, confidence, summary, issues, strengths, next_action.
        outcome is one of: pass, revise, retry, replan, reject.
        """
        user_prompt = self._render(
            "reviewer.j2",
            artifact_content=artifact_content,
            artifact_type=artifact_type,
            stage=stage,
            context=context,
        )
        response = await self._call(user_prompt)
        result = self.extract_json(response)

        # Normalise outcome to enum
        outcome_str = result.get("outcome", "revise").lower()
        try:
            result["outcome_enum"] = ReviewOutcome(outcome_str)
        except ValueError:
            result["outcome_enum"] = ReviewOutcome.REVISE

        return result

    async def classify_failure(self, failure_description: str, stage: str) -> dict:
        """
        Classify a failure and recommend a recovery strategy.

        Returns dict with: classification, root_cause, recovery_strategy, retry_strategy.
        """
        prompt = (
            f"A failure occurred during AEOS workflow stage '{stage}'.\n"
            f"Failure: {failure_description}\n\n"
            "Classify this failure and recommend recovery.\n"
            "Respond with JSON:\n"
            "{\"classification\": \"requirements|planning|design|implementation|verification|"
            "dependency|environment|tooling|infrastructure|external|unknown\",\n"
            " \"root_cause\": \"...\",\n"
            " \"recovery_strategy\": \"...\",\n"
            " \"retry_strategy\": \"what to do differently next time\"}"
        )
        response = await self._call(prompt, complexity=Complexity.MEDIUM)
        return self.extract_json(response)
