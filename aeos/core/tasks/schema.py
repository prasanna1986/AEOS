"""Task schema — lightweight models used by the queue and executor."""

from __future__ import annotations

# Re-export from state schema to keep a single source of truth
from aeos.core.state.schema import (
    TaskRecord,
    TaskStatus,
    FailureRecord,
    FailureClassification,
    ReviewOutcome,
    DecisionRecord,
    LessonLearned,
)

__all__ = [
    "TaskRecord",
    "TaskStatus",
    "FailureRecord",
    "FailureClassification",
    "ReviewOutcome",
    "DecisionRecord",
    "LessonLearned",
]
