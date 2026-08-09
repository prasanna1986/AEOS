"""Git tool -- git operations via GitPython."""

from __future__ import annotations

from pathlib import Path

from aeos.core.tools.shell import run_command, ShellResult


async def git_status(cwd: Path) -> ShellResult:
    return await run_command("git status --short", cwd=cwd)


async def git_diff(cwd: Path, staged: bool = False) -> ShellResult:
    cmd = "git diff --cached" if staged else "git diff"
    return await run_command(cmd, cwd=cwd)


async def git_add(cwd: Path, paths: list[str] | None = None) -> ShellResult:
    target = " ".join(paths) if paths else "."
    return await run_command(f"git add {target}", cwd=cwd)


async def git_commit(cwd: Path, message: str, author_name: str = "AEOS", author_email: str = "aeos@localhost") -> ShellResult:
    import os
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    return await run_command(["git", "commit", "-m", message], cwd=cwd, env=env)


async def git_log(cwd: Path, n: int = 10) -> ShellResult:
    return await run_command(f"git log --oneline -n {n}", cwd=cwd)


async def git_init(cwd: Path) -> ShellResult:
    return await run_command("git init", cwd=cwd)


async def is_git_repo(cwd: Path) -> bool:
    result = await run_command("git rev-parse --git-dir", cwd=cwd, timeout=5)
    return result.success
