"""Artifact store — file-based artifact persistence and retrieval."""

from __future__ import annotations

import json
from pathlib import Path

from aeos.core.artifacts.schema import Artifact, ArtifactType


class ArtifactStore:
    """
    Persists engineering artifacts to .aeos/artifacts/<id>.json.

    Each artifact is stored as a JSON file. The store maintains an in-memory
    index keyed by artifact ID for fast lookup.
    """

    def __init__(self, artifacts_dir: Path) -> None:
        self._dir = artifacts_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, Artifact] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load all existing artifacts from disk into the in-memory index."""
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                artifact = Artifact.model_validate(data)
                self._index[artifact.id] = artifact
            except Exception:
                continue

    def save(self, artifact: Artifact) -> Artifact:
        """Persist an artifact to disk and update the index."""
        from datetime import datetime
        artifact.updated_at = datetime.utcnow()
        path = self._dir / f"{artifact.id}.json"
        path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        self._index[artifact.id] = artifact
        return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        return self._index.get(artifact_id)

    def list_by_type(self, artifact_type: ArtifactType) -> list[Artifact]:
        return [a for a in self._index.values() if a.type == artifact_type]

    def list_by_task(self, task_id: str) -> list[Artifact]:
        return [a for a in self._index.values() if a.task_id == task_id]

    def list_by_stage(self, stage: str) -> list[Artifact]:
        return [a for a in self._index.values() if a.owner_stage == stage]

    def all(self) -> list[Artifact]:
        return list(self._index.values())

    def create(
        self,
        type: ArtifactType,
        title: str,
        content: str = "",
        owner_stage: str = "",
        task_id: str | None = None,
        **kwargs,
    ) -> Artifact:
        """Create a new artifact, persist it, and return it."""
        artifact = Artifact(
            type=type,
            title=title,
            content=content,
            owner_stage=owner_stage,
            task_id=task_id,
            **kwargs,
        )
        return self.save(artifact)

    def update_content(self, artifact_id: str, new_content: str) -> Artifact | None:
        """Update artifact content, increment version, re-persist."""
        artifact = self.get(artifact_id)
        if artifact is None:
            return None
        artifact.update_content(new_content)
        return self.save(artifact)
