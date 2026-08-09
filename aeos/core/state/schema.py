"""State schema — Pydantic models for the full AEOS execution state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FailureClassification(str, Enum):
    REQUIREMENTS = "requirements"
    PLANNING = "planning"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    DEPENDENCY = "dependency"
    ENVIRONMENT = "environment"
    TOOLING = "tooling"
    INFRASTRUCTURE = "infrastructure"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class ReviewOutcome(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    RETRY = "retry"
    REPLAN = "replan"
    REJECT = "reject"


class FailureRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    stage: str
    classification: FailureClassification = FailureClassification.UNKNOWN
    evidence: str = ""
    root_cause: str = ""
    affected_artifacts: list[str] = Field(default_factory=list)
    recovery_strategy: str = ""
    retry_count: int = 0


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    decision: str
    evidence: str = ""
    alternatives: list[str] = Field(default_factory=list)
    tradeoffs: str = ""
    expected_impact: str = ""
    affected_components: list[str] = Field(default_factory=list)


class LessonLearned(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    category: str  # "pattern" | "failure" | "strategy"
    description: str
    context: str = ""


class TaskRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    title: str
    description: str = ""
    objective: str = ""
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 50          # 0–100, higher = more urgent
    complexity: str = "medium"  # high | medium | low
    task_type: str = "coding"   # coding | inference | planning | review | verification
    current_stage: str = "pending"
    dependencies: list[str] = Field(default_factory=list)
    retry_count: int = 0
    failures: list[FailureRecord] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    test_file_path: str | None = None  # TDD: path to generated test file
    impl_file_paths: list[str] = Field(default_factory=list)
    verification_passed: bool = False
    review_outcome: ReviewOutcome | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowStageRecord(BaseModel):
    stage: str
    status: str = "pending"   # pending | active | completed | skipped | failed
    entered_at: datetime | None = None
    completed_at: datetime | None = None
    review_outcome: ReviewOutcome | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class AEOSState(BaseModel):
    """Complete, recoverable execution state for one AEOS project session."""

    session_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    objective: str = ""
    project_root: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Workflow
    current_stage: str = "INITIALIZE"
    activated_stages: list[str] = Field(default_factory=list)
    stage_history: list[WorkflowStageRecord] = Field(default_factory=list)

    # Task graph
    tasks: dict[str, TaskRecord] = Field(default_factory=dict)
    task_queue_order: list[str] = Field(default_factory=list)  # ordered task IDs
    current_task_id: str | None = None

    # Knowledge
    decisions: list[DecisionRecord] = Field(default_factory=list)
    failures: list[FailureRecord] = Field(default_factory=list)
    lessons: list[LessonLearned] = Field(default_factory=list)
    discovered_artifacts: list[str] = Field(default_factory=list)

    # Verification results (stage-level)
    verification_results: dict[str, bool] = Field(default_factory=dict)

    # Pending user questions (critical decisions requiring human input)
    pending_questions: list[dict[str, str]] = Field(default_factory=list)

    # Tool registry
    enabled_tools: list[str] = Field(default_factory=list)

    # Completion
    is_complete: bool = False
    completion_evidence: str = ""

    # Miscellaneous context discovered during execution
    context: dict[str, Any] = Field(default_factory=dict)
