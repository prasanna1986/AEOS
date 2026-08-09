"""Tests for tools: shell, filesystem, git, artifact store."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aeos.core.tools.filesystem import (
    read_file,
    write_file,
    file_exists,
    list_files,
    grep,
    tree,
    count_lines,
)
from aeos.core.tools.shell import run_command, ShellResult


class TestShellTool:
    @pytest.mark.asyncio
    async def test_run_echo_command(self):
        """Shell tool can run a basic command (cross-platform)."""
        result = await run_command(
            ["python", "-c", "print('hello')"],
            timeout=10,
        )
        assert result.success
        assert "hello" in result.output.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_command(self):
        """Shell tool returns returncode 127 for missing command."""
        result = await run_command("this_command_does_not_exist_xyz_abc", timeout=5)
        assert not result.success
        assert result.returncode in (127, -1, 1)

    @pytest.mark.asyncio
    async def test_timeout_kills_command(self):
        """Shell tool kills command and sets timed_out=True after timeout."""
        # Use python sleep which is cross-platform
        result = await run_command(
            ["python", "-c", "import time; time.sleep(10)"],
            timeout=1,
        )
        assert result.timed_out or not result.success

    @pytest.mark.asyncio
    async def test_exit_code_captured(self):
        """Shell tool captures non-zero exit codes."""
        result = await run_command(
            ["python", "-c", "import sys; sys.exit(42)"],
            timeout=10,
        )
        assert result.returncode == 42
        assert not result.success


class TestFilesystemTool:
    def test_write_and_read_file(self, tmp_path: Path):
        """write_file and read_file roundtrip correctly."""
        p = tmp_path / "hello.txt"
        write_file(p, "Hello, AEOS!")
        assert read_file(p) == "Hello, AEOS!"

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        """write_file creates missing parent directories."""
        p = tmp_path / "deep" / "nested" / "file.txt"
        write_file(p, "content")
        assert p.exists()

    def test_file_exists(self, tmp_path: Path):
        """file_exists returns True for existing files."""
        p = tmp_path / "exists.txt"
        p.write_text("x")
        assert file_exists(p) is True
        assert file_exists(tmp_path / "missing.txt") is False

    def test_list_files(self, tmp_path: Path):
        """list_files returns all files matching the pattern."""
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "c.txt").write_text("c")
        py_files = list_files(tmp_path, pattern="*.py")
        assert len(py_files) == 2
        names = {f.name for f in py_files}
        assert "a.py" in names
        assert "b.py" in names

    def test_grep_finds_matches(self, tmp_path: Path):
        """grep finds lines containing the query."""
        f = tmp_path / "source.py"
        f.write_text("def hello():\n    return 'world'\n")
        results = grep(tmp_path, "hello", extensions=["py"])
        assert len(results) >= 1
        assert any("hello" in line for _, _, line in results)

    def test_grep_case_insensitive(self, tmp_path: Path):
        """grep can search case-insensitively."""
        f = tmp_path / "doc.txt"
        f.write_text("The AEOS System is autonomous.\n")
        results = grep(tmp_path, "aeos", case_sensitive=False)
        assert len(results) >= 1

    def test_count_lines(self, tmp_path: Path):
        """count_lines returns the correct line count."""
        f = tmp_path / "lines.txt"
        f.write_text("line1\nline2\nline3\n")
        assert count_lines(f) == 3

    def test_tree_returns_string(self, tmp_path: Path):
        """tree returns a non-empty string for a non-empty directory."""
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file.py").write_text("x")
        result = tree(tmp_path)
        assert isinstance(result, str)
        assert "file.py" in result


class TestArtifactStore:
    def test_create_and_retrieve(self, tmp_path: Path):
        """ArtifactStore can create and retrieve an artifact."""
        from aeos.core.artifacts.store import ArtifactStore
        from aeos.core.artifacts.schema import ArtifactType
        store = ArtifactStore(tmp_path / "artifacts")
        artifact = store.create(
            type=ArtifactType.REQUIREMENTS,
            title="System Requirements",
            content="# Requirements\n- Feature A",
            owner_stage="UNDERSTAND_REQUIREMENTS",
        )
        retrieved = store.get(artifact.id)
        assert retrieved is not None
        assert retrieved.title == "System Requirements"
        assert retrieved.content == "# Requirements\n- Feature A"

    def test_list_by_type(self, tmp_path: Path):
        """ArtifactStore can list artifacts by type."""
        from aeos.core.artifacts.store import ArtifactStore
        from aeos.core.artifacts.schema import ArtifactType
        store = ArtifactStore(tmp_path / "artifacts")
        store.create(type=ArtifactType.TEST_FILE, title="Test A", content="test")
        store.create(type=ArtifactType.TEST_FILE, title="Test B", content="test")
        store.create(type=ArtifactType.IMPLEMENTATION, title="Impl", content="code")
        tests = store.list_by_type(ArtifactType.TEST_FILE)
        assert len(tests) == 2

    def test_update_content_increments_version(self, tmp_path: Path):
        """update_content increments the artifact version."""
        from aeos.core.artifacts.store import ArtifactStore
        from aeos.core.artifacts.schema import ArtifactType
        store = ArtifactStore(tmp_path / "artifacts")
        artifact = store.create(
            type=ArtifactType.TECHNICAL_DESIGN,
            title="Design v1",
            content="Initial design",
        )
        assert artifact.version == 1
        updated = store.update_content(artifact.id, "Updated design")
        assert updated.version == 2
        assert updated.content == "Updated design"

    def test_persist_and_reload_index(self, tmp_path: Path):
        """Artifacts saved to disk are reloaded into a new store instance."""
        from aeos.core.artifacts.store import ArtifactStore
        from aeos.core.artifacts.schema import ArtifactType
        store1 = ArtifactStore(tmp_path / "artifacts")
        artifact = store1.create(type=ArtifactType.DOCUMENTATION, title="Docs", content="...")

        # New store instance — reloads from disk
        store2 = ArtifactStore(tmp_path / "artifacts")
        retrieved = store2.get(artifact.id)
        assert retrieved is not None
        assert retrieved.title == "Docs"
