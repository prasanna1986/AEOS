"""Tools package."""
from aeos.core.tools.shell import run_command, ShellResult
from aeos.core.tools.filesystem import read_file, write_file, list_files, grep, tree, count_lines
from aeos.core.tools.git import git_status, git_diff, git_add, git_commit, git_log, git_init, is_git_repo
from aeos.core.tools.browser import fetch_url, fetch_json

__all__ = [
    "run_command", "ShellResult",
    "read_file", "write_file", "list_files", "grep", "tree", "count_lines",
    "git_status", "git_diff", "git_add", "git_commit", "git_log", "git_init", "is_git_repo",
    "fetch_url", "fetch_json",
]
