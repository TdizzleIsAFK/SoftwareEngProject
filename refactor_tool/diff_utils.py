from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import difflib

from rich.console import Console


@dataclass
class FileChange:
    path: Path
    original: str
    updated: str

    def has_change(self) -> bool:
        return self.original != self.updated

    def unified_diff(self) -> str:
        original_lines = self.original.splitlines(keepends=True)
        updated_lines = self.updated.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile=str(self.path),
            tofile=str(self.path),
            lineterm="",
        )
        return "".join(diff)


class ChangeSet:
    def __init__(self) -> None:
        self._changes: Dict[Path, FileChange] = {}

    def add(self, path: Path, original: str, updated: str) -> None:
        change = FileChange(path=path, original=original, updated=updated)
        if change.has_change():
            self._changes[path] = change

    def merge(self, other: "ChangeSet") -> None:
        for path, change in other._changes.items():
            self._changes[path] = change

    def is_empty(self) -> bool:
        return not self._changes

    def preview(self, console: Console) -> None:
        if self.is_empty():
            console.print("[green]No changes.[/green]")
            return
        for change in self._changes.values():
            diff = change.unified_diff()
            console.print(f"[cyan]Diff for {change.path}[/cyan]")
            if not diff:
                console.print("(binary or no textual diff)")
            else:
                console.print(diff)

    def apply(self, console: Console | None = None) -> None:
        for change in self._changes.values():
            change.path.write_text(change.updated, encoding="utf-8")
        if console:
            console.print(f"[green]Applied {len(self._changes)} file(s).[/green]")


