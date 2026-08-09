"""State manager -- load, save, and recover AEOS execution state."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from aeos.core.state.schema import AEOSState

_STATE_FILE = "state.json"
_BACKUP_FILE = "state.backup.json"


class StateManager:
    """
    Persists and recovers AEOS execution state to/from .aeos/state.json.

    On every save, the previous state is atomically backed up to state.backup.json
    so that interrupted runs can always be recovered.
    """

    def __init__(self, workspace_dir: Path) -> None:
        self._workspace = workspace_dir
        self._state_path = workspace_dir / _STATE_FILE
        self._backup_path = workspace_dir / _BACKUP_FILE

    def exists(self) -> bool:
        return self._state_path.exists()

    def load(self) -> AEOSState:
        """Load state from disk. Returns fresh state if none exists."""
        if not self._state_path.exists():
            return AEOSState()
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            return AEOSState.model_validate(raw)
        except Exception:
            # Try backup
            if self._backup_path.exists():
                raw = json.loads(self._backup_path.read_text(encoding="utf-8"))
                return AEOSState.model_validate(raw)
            raise

    def save(self, state: AEOSState) -> None:
        """Atomically save state to disk with backup."""
        state.updated_at = datetime.utcnow()
        self._workspace.mkdir(parents=True, exist_ok=True)

        # Rotate backup
        if self._state_path.exists():
            shutil.copy2(self._state_path, self._backup_path)

        # Write to temp then rename (atomic on most OSes)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._state_path)

    def reset(self, objective: str, project_root: str) -> AEOSState:
        """Start a fresh session, archiving any previous state."""
        if self._state_path.exists():
            archive = self._workspace / f"state.{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            shutil.copy2(self._state_path, archive)

        state = AEOSState(objective=objective, project_root=project_root)
        self.save(state)
        return state

    def update_stage(self, state: AEOSState, stage: str) -> AEOSState:
        from aeos.core.state.schema import WorkflowStageRecord
        state.current_stage = stage
        # Mark stage as active in history
        for record in state.stage_history:
            if record.stage == stage:
                record.status = "active"
                record.entered_at = datetime.utcnow()
                break
        else:
            state.stage_history.append(
                WorkflowStageRecord(stage=stage, status="active", entered_at=datetime.utcnow())
            )
        self.save(state)
        return state
