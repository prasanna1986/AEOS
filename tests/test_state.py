"""Tests for State schema and StateManager persistence."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import pytest

from aeos.core.state.schema import (
    AEOSState,
    TaskRecord,
    TaskStatus,
    FailureRecord,
    FailureClassification,
    ReviewOutcome,
    DecisionRecord,
    LessonLearned,
)
from aeos.core.state.manager import StateManager


class TestTaskRecord:
    def test_default_values(self):
        """TaskRecord has sensible defaults."""
        task = TaskRecord(title="My Task")
        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 0
        assert task.verification_passed is False
        assert task.priority == 50
        assert isinstance(task.id, str)
        assert len(task.id) == 8

    def test_tdd_fields(self):
        """TaskRecord has TDD-specific fields."""
        task = TaskRecord(title="TDD Task", test_file_path="tests/test_foo.py")
        assert task.test_file_path == "tests/test_foo.py"
        assert task.impl_file_paths == []

    def test_failure_recording(self):
        """Failures can be appended to a task."""
        task = TaskRecord(title="Failing Task")
        failure = FailureRecord(
            stage="tdd_green",
            classification=FailureClassification.IMPLEMENTATION,
            evidence="Tests failed: AssertionError",
            root_cause="Off-by-one error in loop",
        )
        task.failures.append(failure)
        assert len(task.failures) == 1
        assert task.failures[0].classification == FailureClassification.IMPLEMENTATION


class TestAEOSState:
    def test_fresh_state(self):
        """Fresh state has correct defaults."""
        state = AEOSState(objective="Build something", project_root="/tmp/proj")
        assert state.current_stage == "INITIALIZE"
        assert state.is_complete is False
        assert state.tasks == {}
        assert state.decisions == []
        assert state.lessons == []

    def test_add_task(self):
        """Tasks can be added to state."""
        state = AEOSState(objective="Test", project_root="/tmp")
        task = TaskRecord(title="Task 1", description="Do thing")
        state.tasks[task.id] = task
        state.task_queue_order.append(task.id)
        assert task.id in state.tasks
        assert task.id in state.task_queue_order

    def test_decision_recording(self):
        """Decisions can be appended."""
        state = AEOSState(objective="Test", project_root="/tmp")
        decision = DecisionRecord(
            decision="Use PostgreSQL over SQLite",
            evidence="Need concurrent writes",
            tradeoffs="More complex setup",
        )
        state.decisions.append(decision)
        assert len(state.decisions) == 1

    def test_lesson_recording(self):
        """Lessons can be appended."""
        state = AEOSState(objective="Test", project_root="/tmp")
        lesson = LessonLearned(
            category="pattern",
            description="Always write tests before implementation",
        )
        state.lessons.append(lesson)
        assert len(state.lessons) == 1
        assert state.lessons[0].category == "pattern"


class TestStateManager:
    def test_exists_false_on_new_workspace(self, tmp_workspace: Path):
        """StateManager reports no state when workspace is empty."""
        sm = StateManager(tmp_workspace)
        assert sm.exists() is False

    def test_save_and_load_roundtrip(self, state_manager, fresh_state):
        """State survives a save/load roundtrip."""
        fresh_state.objective = "Roundtrip test"
        state_manager.save(fresh_state)
        loaded = state_manager.load()
        assert loaded.objective == "Roundtrip test"
        assert loaded.session_id == fresh_state.session_id

    def test_save_with_tasks(self, state_manager, fresh_state):
        """Tasks are preserved across save/load."""
        task = TaskRecord(
            title="Saved Task",
            status=TaskStatus.COMPLETED,
            verification_passed=True,
        )
        fresh_state.tasks[task.id] = task
        state_manager.save(fresh_state)
        loaded = state_manager.load()
        assert task.id in loaded.tasks
        assert loaded.tasks[task.id].status == TaskStatus.COMPLETED
        assert loaded.tasks[task.id].verification_passed is True

    def test_backup_created_on_second_save(self, state_manager, fresh_state, tmp_workspace):
        """A backup file is created on the second save."""
        state_manager.save(fresh_state)
        fresh_state.objective = "Updated objective"
        state_manager.save(fresh_state)
        backup = tmp_workspace / "state.backup.json"
        assert backup.exists()

    def test_reset_creates_fresh_state(self, state_manager, tmp_workspace):
        """Reset creates a fresh state with the given objective."""
        old_state = AEOSState(objective="Old", project_root="/tmp")
        state_manager.save(old_state)

        new_state = state_manager.reset(objective="New objective", project_root="/tmp/new")
        assert new_state.objective == "New objective"
        assert new_state.session_id != old_state.session_id

    def test_recover_from_backup_on_corrupt_state(self, tmp_workspace: Path):
        """If state.json is corrupt, loader falls back to backup."""
        sm = StateManager(tmp_workspace)
        good_state = AEOSState(objective="Good state", project_root="/tmp")
        sm.save(good_state)
        sm.save(good_state)  # creates backup

        # Corrupt the main state file
        (tmp_workspace / "state.json").write_text("{ invalid json !!!", encoding="utf-8")

        loaded = sm.load()
        assert loaded.objective == "Good state"

    def test_update_stage(self, state_manager, fresh_state):
        """update_stage changes current_stage and records history."""
        state_manager.save(fresh_state)
        updated = state_manager.update_stage(fresh_state, "DISCOVER_CONTEXT")
        assert updated.current_stage == "DISCOVER_CONTEXT"
        stage_names = [s.stage for s in updated.stage_history]
        assert "DISCOVER_CONTEXT" in stage_names
