"""Shell tool — safe command execution with timeout and output capture."""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ShellResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined stdout + stderr for display."""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(self.stderr.strip())
        return "\n".join(parts)


async def run_command(
    command: str | list[str],
    cwd: Path | str | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> ShellResult:
    """
    Execute a shell command asynchronously.

    Args:
        command: Command string (shell-parsed) or list of args.
        cwd: Working directory for the command.
        timeout: Seconds before the command is killed.
        env: Optional environment variable overrides.

    Returns:
        ShellResult with returncode, stdout, stderr.
    """
    if isinstance(command, str):
        args = shlex.split(command)
    else:
        args = command

    cmd_str = " ".join(args) if isinstance(args, list) else command

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return ShellResult(
                command=cmd_str,
                returncode=proc.returncode or 0,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ShellResult(
                command=cmd_str,
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                timed_out=True,
            )
    except FileNotFoundError:
        return ShellResult(
            command=cmd_str,
            returncode=127,
            stdout="",
            stderr=f"Command not found: {args[0]}",
        )


def run_command_sync(
    command: str | list[str],
    cwd: Path | str | None = None,
    timeout: int = 60,
) -> ShellResult:
    """Synchronous wrapper for use outside async contexts."""
    return asyncio.run(run_command(command, cwd=cwd, timeout=timeout))
