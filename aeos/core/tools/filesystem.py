"""Filesystem tool -- read, write, search, tree."""

from __future__ import annotations

import fnmatch
from pathlib import Path


def read_file(path: Path | str, encoding: str = "utf-8") -> str:
    return Path(path).read_text(encoding=encoding)


def write_file(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)


def file_exists(path: Path | str) -> bool:
    return Path(path).exists()


def list_files(
    directory: Path | str,
    pattern: str = "*",
    recursive: bool = True,
    exclude: list[str] | None = None,
) -> list[Path]:
    """List files matching a glob pattern, optionally recursive."""
    root = Path(directory)
    exclude = exclude or []
    if recursive:
        candidates = root.rglob(pattern)
    else:
        candidates = root.glob(pattern)

    results = []
    for p in candidates:
        if p.is_file():
            rel = str(p.relative_to(root))
            if not any(fnmatch.fnmatch(rel, ex) for ex in exclude):
                results.append(p)
    return sorted(results)


def grep(
    directory: Path | str,
    query: str,
    extensions: list[str] | None = None,
    case_sensitive: bool = False,
) -> list[tuple[Path, int, str]]:
    """
    Search for a string across files.

    Returns: list of (file_path, line_number, line_content)
    """
    results = []
    root = Path(directory)
    pattern = "*" if not extensions else None

    files: list[Path] = []
    if extensions:
        for ext in extensions:
            files.extend(root.rglob(f"*.{ext.lstrip('.')}"))
    else:
        files = list(root.rglob("*"))

    search_q = query if case_sensitive else query.lower()

    for f in files:
        if not f.is_file():
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                haystack = line if case_sensitive else line.lower()
                if search_q in haystack:
                    results.append((f, i, line))
        except Exception:
            continue
    return results


def tree(directory: Path | str, max_depth: int = 4, exclude: list[str] | None = None) -> str:
    """Return a tree-style string representation of the directory."""
    root = Path(directory)
    exclude_set = set(exclude or [".git", "__pycache__", "node_modules", ".aeos", "*.pyc"])

    def _should_exclude(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pat) for pat in exclude_set)

    lines = [str(root)]

    def _walk(path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        children = [c for c in children if not _should_exclude(c.name)]
        for i, child in enumerate(children):
            connector = "?-- " if i == len(children) - 1 else "?-- "
            lines.append(f"{prefix}{connector}{child.name}")
            if child.is_dir():
                extension = "    " if i == len(children) - 1 else "?   "
                _walk(child, prefix + extension, depth + 1)

    _walk(root, "", 0)
    return "\n".join(lines)


def count_lines(path: Path | str) -> int:
    try:
        return len(Path(path).read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0
