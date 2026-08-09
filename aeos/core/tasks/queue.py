"""Priority task queue with dependency tracking."""

from __future__ import annotations

from collections import defaultdict

from aeos.core.state.schema import AEOSState, TaskRecord, TaskStatus


class TaskQueue:
    """
    Ordered priority queue built on top of the AEOSState task graph.

    Provides:
    - Dependency-aware ready-task selection
    - Priority ordering (higher priority = dequeued first)
    - Blocked/unblocked task tracking
    """

    def __init__(self, state: AEOSState) -> None:
        self._state = state

    # -- Query helpers ----------------------------------------

    def pending_task_ids(self) -> list[str]:
        """Return IDs of tasks that are PENDING or READY, ordered by priority."""
        candidates = [
            tid for tid in self._state.task_queue_order
            if self._state.tasks.get(tid, TaskRecord(title="")).status
            in (TaskStatus.PENDING, TaskStatus.READY)
        ]
        return sorted(
            candidates,
            key=lambda tid: self._state.tasks[tid].priority,
            reverse=True,
        )

    def next_ready_task(self) -> TaskRecord | None:
        """Return the highest-priority task whose dependencies are all complete."""
        for tid in self.pending_task_ids():
            task = self._state.tasks[tid]
            if self._dependencies_met(task):
                return task
        return None

    def all_done(self) -> bool:
        """Return True if every task is COMPLETED or SKIPPED."""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for t in self._state.tasks.values()
        )

    def failed_tasks(self) -> list[TaskRecord]:
        return [t for t in self._state.tasks.values() if t.status == TaskStatus.FAILED]

    def blocked_tasks(self) -> list[TaskRecord]:
        return [t for t in self._state.tasks.values() if t.status == TaskStatus.BLOCKED]

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for t in self._state.tasks.values():
            counts[t.status.value] += 1
        return dict(counts)

    # -- Mutation helpers -------------------------------------

    def enqueue(self, task: TaskRecord, prepend: bool = False) -> None:
        """Add a task to the queue."""
        self._state.tasks[task.id] = task
        if task.id not in self._state.task_queue_order:
            if prepend:
                self._state.task_queue_order.insert(0, task.id)
            else:
                self._state.task_queue_order.append(task.id)

    def mark_ready(self, task_id: str) -> None:
        if task_id in self._state.tasks:
            self._state.tasks[task_id].status = TaskStatus.READY

    def unblock_children(self, completed_task: TaskRecord) -> list[str]:
        """
        After a parent task completes, check which of its children are now
        unblocked (all dependencies met). Returns IDs of newly unblocked tasks.
        """
        unblocked = []
        for child_id in completed_task.child_ids:
            child = self._state.tasks.get(child_id)
            if child and child.status == TaskStatus.BLOCKED:
                if self._dependencies_met(child):
                    child.status = TaskStatus.READY
                    unblocked.append(child_id)
        return unblocked

    # -- Internal ---------------------------------------------

    def _dependencies_met(self, task: TaskRecord) -> bool:
        for dep_id in task.dependencies:
            dep = self._state.tasks.get(dep_id)
            if dep and dep.status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
                return False
        return True
