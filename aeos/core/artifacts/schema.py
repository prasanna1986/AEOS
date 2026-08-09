"""Artifact schema — structured engineering artifact models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    PROJECT_PLAN = "project_plan"
    TASK_GRAPH = "task_graph"
    TECHNICAL_DESIGN = "technical_design"
    DECISION_LOG = "decision_log"
    RISK_REGISTER = "risk_register"
    TEST_PLAN = "test_plan"
    TEST_FILE = "test_file"
    IMPLEMENTATION = "implementation"
    VERIFICATION_REPORT = "verification_report"
    DOCUMENTATION = "documentation"
    DEPLOYMENT_PLAN = "deployment_plan"
    RELEASE_NOTES = "release_notes"
    LESSONS_LEARNED = "lessons_learned"


class ArtifactStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class Artifact(BaseModel):
    """A structured engineering artifact produced during the workflow."""

    id: str = Field(default_factory=lambda: str(uuid4())[:12])
    type: ArtifactType
    title: str
    content: str = ""
    file_path: str | None = None     # path on disk if persisted as a file

    # Metadata
    version: int = 1
    status: ArtifactStatus = ArtifactStatus.DRAFT
    owner_stage: str = ""            # which workflow stage produced this
    task_id: str | None = None       # associated task, if any

    # Review state
    review_status: str = "pending"   # pending | passed | failed
    review_notes: str = ""

    # Verification state
    verification_state: str = "unverified"  # unverified | passed | failed
    verification_notes: str = ""

    # Dependencies on other artifacts
    depends_on: list[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional structured metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_content(self, new_content: str) -> None:
        self.content = new_content
        self.version += 1
        self.updated_at = datetime.utcnow()
        self.status = ArtifactStatus.DRAFT  # needs re-review after update
