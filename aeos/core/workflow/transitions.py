"""Stage transition rules -- (stage, review_outcome) -> next_stage."""

from __future__ import annotations

from aeos.core.state.schema import ReviewOutcome
from aeos.core.workflow.stages import WorkflowStage

# Transition table: (current_stage, review_outcome) -> next_stage
TRANSITIONS: dict[tuple[WorkflowStage, ReviewOutcome], WorkflowStage] = {
    # -- UNDERSTAND_REQUIREMENTS --
    (WorkflowStage.UNDERSTAND_REQUIREMENTS, ReviewOutcome.PASS): WorkflowStage.REVIEW_REQUIREMENTS,
    (WorkflowStage.REVIEW_REQUIREMENTS, ReviewOutcome.PASS): WorkflowStage.PROJECT_PLANNING,
    (WorkflowStage.REVIEW_REQUIREMENTS, ReviewOutcome.REVISE): WorkflowStage.UNDERSTAND_REQUIREMENTS,
    (WorkflowStage.REVIEW_REQUIREMENTS, ReviewOutcome.REPLAN): WorkflowStage.DISCOVER_CONTEXT,
    (WorkflowStage.REVIEW_REQUIREMENTS, ReviewOutcome.REJECT): WorkflowStage.DISCOVER_CONTEXT,

    # -- PROJECT_PLANNING --
    (WorkflowStage.PROJECT_PLANNING, ReviewOutcome.PASS): WorkflowStage.REVIEW_PROJECT_PLAN,
    (WorkflowStage.REVIEW_PROJECT_PLAN, ReviewOutcome.PASS): WorkflowStage.PROJECT_DECOMPOSITION,
    (WorkflowStage.REVIEW_PROJECT_PLAN, ReviewOutcome.REVISE): WorkflowStage.PROJECT_PLANNING,
    (WorkflowStage.REVIEW_PROJECT_PLAN, ReviewOutcome.RETRY): WorkflowStage.PROJECT_PLANNING,
    (WorkflowStage.REVIEW_PROJECT_PLAN, ReviewOutcome.REPLAN): WorkflowStage.UNDERSTAND_REQUIREMENTS,
    (WorkflowStage.REVIEW_PROJECT_PLAN, ReviewOutcome.REJECT): WorkflowStage.UNDERSTAND_REQUIREMENTS,

    # -- PROJECT_DECOMPOSITION --
    (WorkflowStage.PROJECT_DECOMPOSITION, ReviewOutcome.PASS): WorkflowStage.REVIEW_DECOMPOSITION,
    (WorkflowStage.REVIEW_DECOMPOSITION, ReviewOutcome.PASS): WorkflowStage.TASK_QUEUE,
    (WorkflowStage.REVIEW_DECOMPOSITION, ReviewOutcome.REVISE): WorkflowStage.PROJECT_DECOMPOSITION,
    (WorkflowStage.REVIEW_DECOMPOSITION, ReviewOutcome.RETRY): WorkflowStage.PROJECT_DECOMPOSITION,
    (WorkflowStage.REVIEW_DECOMPOSITION, ReviewOutcome.REPLAN): WorkflowStage.PROJECT_PLANNING,

    # -- TASK_EXECUTION_ENGINE --
    (WorkflowStage.TASK_EXECUTION_ENGINE, ReviewOutcome.PASS): WorkflowStage.SYSTEM_INTEGRATION,

    # -- SYSTEM_INTEGRATION / REVIEW --
    (WorkflowStage.SYSTEM_INTEGRATION, ReviewOutcome.PASS): WorkflowStage.SYSTEM_REVIEW,
    (WorkflowStage.SYSTEM_REVIEW, ReviewOutcome.PASS): WorkflowStage.FINAL_VERIFICATION,
    (WorkflowStage.SYSTEM_REVIEW, ReviewOutcome.REVISE): WorkflowStage.TASK_EXECUTION_ENGINE,
    (WorkflowStage.SYSTEM_REVIEW, ReviewOutcome.REPLAN): WorkflowStage.PROJECT_PLANNING,

    # -- FINAL_VERIFICATION --
    (WorkflowStage.FINAL_VERIFICATION, ReviewOutcome.PASS): WorkflowStage.COMPLETE,
    (WorkflowStage.FINAL_VERIFICATION, ReviewOutcome.REVISE): WorkflowStage.TASK_EXECUTION_ENGINE,
    (WorkflowStage.FINAL_VERIFICATION, ReviewOutcome.REPLAN): WorkflowStage.PROJECT_PLANNING,
}


def get_next_stage(
    current: WorkflowStage,
    outcome: ReviewOutcome,
) -> WorkflowStage:
    """
    Return the next workflow stage given the current stage and review outcome.
    Falls back to REVISE behaviour (return to current) if no explicit rule found.
    """
    return TRANSITIONS.get((current, outcome), current)
