"""Standalone task decomposer — wraps the DecomposerAgent with queue integration."""

from __future__ import annotations

from uuid import uuid4

from aeos.core.agents.decomposer import DecomposerAgent
from aeos.core.state.schema import AEOSState, TaskRecord, TaskStatus
from aeos.core.state.manager import StateManager
from aeos.core.tasks.queue import TaskQueue


class TaskDecomposer:
    """
    Recursively decomposes tasks until every work item is atomic:
    - Single objective
    - Independently verifiable
    - Under the configured LoC threshold
    - Subtasks ordered: verification-design → implementation → verification-run (TDD)
    """

    def __init__(
        self,
        decomposer_agent: DecomposerAgent,
        state: AEOSState,
        state_manager: StateManager,
        decompose_threshold: int = 300,
        max_depth: int = 5,
    ) -> None:
        self._agent = decomposer_agent
        self._state = state
        self._sm = state_manager
        self._threshold = decompose_threshold
        self._max_depth = max_depth
        self._queue = TaskQueue(state)

    async def decompose_all(self) -> None:
        """Decompose all pending tasks in the queue that exceed the threshold."""
        pending = list(self._queue.pending_task_ids())
        for tid in pending:
            task = self._state.tasks.get(tid)
            if task and self._should_decompose(task):
                await self._decompose_task(task, depth=0)
        self._sm.save(self._state)

    async def _decompose_task(self, task: TaskRecord, depth: int) -> None:
        """Recursively decompose a task into atomic subtasks."""
        if depth >= self._max_depth:
            return  # Safety: don't recurse infinitely

        result = await self._agent.decompose(task, self._threshold)

        if not result.get("should_decompose"):
            return  # Task is already atomic

        subtasks_data = result.get("subtasks", [])
        if not subtasks_data:
            return

        # Create child task records
        child_ids: list[str] = []
        id_map: dict[str, str] = {}  # title → generated ID (for dependency resolution)

        for sub_data in subtasks_data:
            sub_id = str(uuid4())[:8]
            id_map[sub_data["title"]] = sub_id
            child_ids.append(sub_id)

        for sub_data in subtasks_data:
            sub_id = id_map[sub_data["title"]]

            # Resolve dependency titles → IDs
            dep_ids = [
                id_map[dep_title]
                for dep_title in sub_data.get("dependencies", [])
                if dep_title in id_map
            ]
            # Also inherit parent's dependencies for the first child
            if not dep_ids and child_ids and child_ids[0] == sub_id:
                dep_ids = list(task.dependencies)

            sub = TaskRecord(
                id=sub_id,
                title=sub_data["title"],
                description=sub_data.get("description", ""),
                objective=sub_data.get("objective", ""),
                parent_id=task.id,
                complexity=sub_data.get("complexity", "low"),
                task_type=sub_data.get("task_type", "coding"),
                priority=sub_data.get("priority", task.priority - 5),
                dependencies=dep_ids,
                metadata={
                    "tdd_phase": sub_data.get("tdd_phase", ""),
                    "estimated_loc": sub_data.get("estimated_loc", 0),
                },
            )

            self._queue.enqueue(sub, prepend=True)

            # Recurse if subtask is still too large
            if self._should_decompose(sub):
                await self._decompose_task(sub, depth + 1)

        # Mark parent as blocked (waiting for children)
        task.child_ids = child_ids
        task.status = TaskStatus.BLOCKED
        self._state.tasks[task.id] = task

    def _should_decompose(self, task: TaskRecord) -> bool:
        """Return True if the task should be broken down further."""
        estimated_loc = task.metadata.get("estimated_loc", 0)
        return (
            task.complexity == "high"
            or estimated_loc > self._threshold
        )
