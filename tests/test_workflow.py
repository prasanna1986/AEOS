"""Tests for workflow stages, transitions, and task queue."""

from __future__ import annotations

import pytest

from aeos.core.workflow.stages import WorkflowStage, CORE_LIFECYCLE, ARTIFACT_STAGE_MAP
from aeos.core.workflow.transitions import get_next_stage
from aeos.core.state.schema import ReviewOutcome, TaskRecord, TaskStatus, AEOSState
from aeos.core.tasks.queue import TaskQueue


class TestWorkflowStages:
    def test_core_lifecycle_starts_with_initialize(self):
        """Core lifecycle must start with INITIALIZE."""
        assert CORE_LIFECYCLE[0] == WorkflowStage.INITIALIZE

    def test_core_lifecycle_ends_with_complete(self):
        """Core lifecycle must end with COMPLETE."""
        assert CORE_LIFECYCLE[-1] == WorkflowStage.COMPLETE

    def test_all_core_stages_are_defined(self):
        """Every stage in the core lifecycle must be a valid WorkflowStage."""
        for stage in CORE_LIFECYCLE:
            assert isinstance(stage, WorkflowStage)

    def test_artifact_stage_map_has_entries(self):
        """Dynamic stage map must have at least one entry."""
        assert len(ARTIFACT_STAGE_MAP) > 0

    def test_artifact_stage_map_values_are_workflow_stages(self):
        """All values in ARTIFACT_STAGE_MAP must be WorkflowStage instances."""
        for value in ARTIFACT_STAGE_MAP.values():
            assert isinstance(value, WorkflowStage)


class TestTransitions:
    def test_review_requirements_pass_advances(self):
        """PASS on REVIEW_REQUIREMENTS advances to PROJECT_PLANNING."""
        next_stage = get_next_stage(WorkflowStage.REVIEW_REQUIREMENTS, ReviewOutcome.PASS)
        assert next_stage == WorkflowStage.PROJECT_PLANNING

    def test_review_requirements_revise_returns_to_understand(self):
        """REVISE on REVIEW_REQUIREMENTS returns to UNDERSTAND_REQUIREMENTS."""
        next_stage = get_next_stage(WorkflowStage.REVIEW_REQUIREMENTS, ReviewOutcome.REVISE)
        assert next_stage == WorkflowStage.UNDERSTAND_REQUIREMENTS

    def test_review_project_plan_pass_advances(self):
        """PASS on REVIEW_PROJECT_PLAN advances to PROJECT_DECOMPOSITION."""
        next_stage = get_next_stage(WorkflowStage.REVIEW_PROJECT_PLAN, ReviewOutcome.PASS)
        assert next_stage == WorkflowStage.PROJECT_DECOMPOSITION

    def test_review_project_plan_revise_returns_to_planning(self):
        """REVISE on REVIEW_PROJECT_PLAN returns to PROJECT_PLANNING."""
        next_stage = get_next_stage(WorkflowStage.REVIEW_PROJECT_PLAN, ReviewOutcome.REVISE)
        assert next_stage == WorkflowStage.PROJECT_PLANNING

    def test_final_verification_pass_completes(self):
        """PASS on FINAL_VERIFICATION reaches COMPLETE."""
        next_stage = get_next_stage(WorkflowStage.FINAL_VERIFICATION, ReviewOutcome.PASS)
        assert next_stage == WorkflowStage.COMPLETE

    def test_final_verification_revise_returns_to_execution(self):
        """REVISE on FINAL_VERIFICATION returns to TASK_EXECUTION_ENGINE."""
        next_stage = get_next_stage(WorkflowStage.FINAL_VERIFICATION, ReviewOutcome.REVISE)
        assert next_stage == WorkflowStage.TASK_EXECUTION_ENGINE

    def test_unknown_transition_stays_at_current(self):
        """Unknown (stage, outcome) pairs stay at the current stage."""
        result = get_next_stage(WorkflowStage.INITIALIZE, ReviewOutcome.PASS)
        # INITIALIZE PASS is not in the table → stays at INITIALIZE
        assert result == WorkflowStage.INITIALIZE


class TestTaskQueue:
    def _make_state_with_tasks(self, tasks: list[TaskRecord]) -> AEOSState:
        state = AEOSState(objective="Test", project_root="/tmp")
        for t in tasks:
            state.tasks[t.id] = t
            state.task_queue_order.append(t.id)
        return state

    def test_pending_task_ids_returns_pending_tasks(self):
        """pending_task_ids returns only PENDING/READY tasks."""
        t1 = TaskRecord(title="T1", status=TaskStatus.PENDING, priority=80)
        t2 = TaskRecord(title="T2", status=TaskStatus.COMPLETED, priority=90)
        t3 = TaskRecord(title="T3", status=TaskStatus.READY, priority=70)
        state = self._make_state_with_tasks([t1, t2, t3])
        queue = TaskQueue(state)
        pending = queue.pending_task_ids()
        assert t1.id in pending
        assert t3.id in pending
        assert t2.id not in pending

    def test_pending_task_ids_sorted_by_priority(self):
        """pending_task_ids returns tasks sorted highest priority first."""
        t_low = TaskRecord(title="Low", status=TaskStatus.PENDING, priority=20)
        t_high = TaskRecord(title="High", status=TaskStatus.PENDING, priority=90)
        t_mid = TaskRecord(title="Mid", status=TaskStatus.PENDING, priority=50)
        state = self._make_state_with_tasks([t_low, t_high, t_mid])
        queue = TaskQueue(state)
        pending = queue.pending_task_ids()
        priorities = [state.tasks[tid].priority for tid in pending]
        assert priorities == sorted(priorities, reverse=True)

    def test_next_ready_task_respects_dependencies(self):
        """next_ready_task skips tasks whose dependencies are not complete."""
        dep = TaskRecord(title="Dependency", status=TaskStatus.PENDING, priority=50)
        child = TaskRecord(
            title="Child", status=TaskStatus.PENDING, priority=90,
            dependencies=[dep.id],
        )
        state = self._make_state_with_tasks([dep, child])
        queue = TaskQueue(state)
        # child has unmet dependency → dep should be returned
        ready = queue.next_ready_task()
        assert ready is not None
        assert ready.id == dep.id

    def test_next_ready_task_none_when_all_blocked(self):
        """next_ready_task returns None when all tasks have unmet dependencies."""
        dep = TaskRecord(title="Dep", status=TaskStatus.PENDING)
        child = TaskRecord(title="Child", status=TaskStatus.PENDING, dependencies=[dep.id])
        dep.status = TaskStatus.BLOCKED  # make dep blocked too
        state = self._make_state_with_tasks([dep, child])
        queue = TaskQueue(state)
        assert queue.next_ready_task() is None

    def test_all_done_false_when_pending(self):
        """all_done returns False when tasks are still pending."""
        t = TaskRecord(title="T", status=TaskStatus.PENDING)
        state = self._make_state_with_tasks([t])
        queue = TaskQueue(state)
        assert queue.all_done() is False

    def test_all_done_true_when_all_complete(self):
        """all_done returns True when all tasks are COMPLETED."""
        t1 = TaskRecord(title="T1", status=TaskStatus.COMPLETED)
        t2 = TaskRecord(title="T2", status=TaskStatus.SKIPPED)
        state = self._make_state_with_tasks([t1, t2])
        queue = TaskQueue(state)
        assert queue.all_done() is True

    def test_stats_counts_by_status(self):
        """stats() returns counts per status."""
        t1 = TaskRecord(title="T1", status=TaskStatus.COMPLETED)
        t2 = TaskRecord(title="T2", status=TaskStatus.PENDING)
        t3 = TaskRecord(title="T3", status=TaskStatus.FAILED)
        state = self._make_state_with_tasks([t1, t2, t3])
        queue = TaskQueue(state)
        stats = queue.stats()
        assert stats["completed"] == 1
        assert stats["pending"] == 1
        assert stats["failed"] == 1

    def test_enqueue_adds_task(self):
        """enqueue adds a new task to state and queue order."""
        state = AEOSState(objective="Test", project_root="/tmp")
        queue = TaskQueue(state)
        task = TaskRecord(title="New Task")
        queue.enqueue(task)
        assert task.id in state.tasks
        assert task.id in state.task_queue_order

    def test_enqueue_prepend(self):
        """enqueue with prepend=True places task at front of queue."""
        state = AEOSState(objective="Test", project_root="/tmp")
        queue = TaskQueue(state)
        t1 = TaskRecord(title="T1")
        t2 = TaskRecord(title="T2 (prepend)")
        queue.enqueue(t1)
        queue.enqueue(t2, prepend=True)
        assert state.task_queue_order[0] == t2.id
