from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, List
import fnmatch


DEFAULT_EXCLUDES = [
    "**/.venv/**",
    "**/venv/**",
    "**/__pycache__/**",
    "**/.git/**",
]


def _matches_any(path: Path, patterns: List[str]) -> bool:
    s = str(path.as_posix())
    return any(fnmatch.fnmatch(s, pat) for pat in patterns)


def discover_python_files(
    root: Path, include: List[str] | None, exclude: List[str] | None
) -> Iterator[Path]:
    inc = include or ["**/*.py"]
    exc = (exclude or []) + DEFAULT_EXCLUDES
    seen: set[Path] = set()
    for pattern in inc:
        for p in root.rglob("*.py"):
            if _matches_any(p, exc):
                continue
            if not _matches_any(p, [pattern]):
                continue
            if p not in seen:
                seen.add(p)
                yield p


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def module_path_from_file(root: Path, file_path: Path) -> str | None:
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return None
    parts = list(rel.parts)
    if not parts:
        return None
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    # Drop any empty or __init__ specifics
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


