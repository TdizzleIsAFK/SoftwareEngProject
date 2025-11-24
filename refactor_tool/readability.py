from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple
import re

import libcst as cst

from .diff_utils import ChangeSet
from .project import read_text


HIDDEN_CHARS_PATTERN = re.compile(
    "[\u200B\u200C\u200D\uFEFF]"  # zero width space, non-joiners, BOM
)


def _normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _strip_hidden(text: str) -> str:
    return HIDDEN_CHARS_PATTERN.sub("", text)


def _remove_dead_imports_in_module(text: str) -> str:
    try:
        mod = cst.parse_module(text)
    except Exception:
        return text

    used_names: set[str] = set()

    class Usage(cst.CSTVisitor):
        def visit_Name(self, node: cst.Name):
            used_names.add(node.value)

    mod.visit(Usage())

    class Prune(cst.CSTTransformer):
        def leave_ImportFrom(self, node: cst.ImportFrom, updated: cst.ImportFrom):
            # Keep star imports as-is
            if any(isinstance(n, cst.ImportStar) for n in node.names):
                return updated
            new_names = []
            for alias in node.names:
                if isinstance(alias.name, cst.Name) and alias.name.value in used_names:
                    new_names.append(alias)
                elif isinstance(alias, cst.ImportAlias) and alias.asname:
                    # keep aliases if alias name used
                    alias_name = alias.asname.name.value
                    if alias_name in used_names:
                        new_names.append(alias)
            if not new_names:
                return None
            return updated.with_changes(names=tuple(new_names))

        def leave_Import(self, node: cst.Import, updated: cst.Import):
            new_names = []
            for alias in node.names:
                alias_name = (alias.asname.name.value if alias.asname else alias.name.value.split(".")[-1])
                if alias_name in used_names:
                    new_names.append(alias)
            if not new_names:
                return None
            return updated.with_changes(names=tuple(new_names))

    new_mod = mod.visit(Prune())
    return new_mod.code


def find_potential_dead_imports(path: Path, text: str) -> List[Tuple[str, int, str]]:
    results: List[Tuple[str, int, str]] = []
    try:
        mod = cst.parse_module(text)
    except Exception:
        return results
    used_names: set[str] = set()

    class Usage(cst.CSTVisitor):
        def visit_Name(self, node: cst.Name):
            used_names.add(node.value)

    mod.visit(Usage())

    class Checker(cst.CSTVisitor):
        def visit_ImportFrom(self, node: cst.ImportFrom):
            if any(isinstance(n, cst.ImportStar) for n in node.names):
                return None
            for alias in node.names:
                if isinstance(alias.name, cst.Name):
                    name = alias.asname.name.value if alias.asname else alias.name.value
                    if name not in used_names:
                        results.append((str(path), node.get_lines()[0], name))
            return None

        def visit_Import(self, node: cst.Import):
            for alias in node.names:
                name = alias.asname.name.value if alias.asname else alias.name.value.split(".")[-1]
                if name not in used_names:
                    results.append((str(path), node.get_lines()[0], name))
            return None

    mod.visit(Checker())
    return results


def tidy_files(
    files: List[Path],
    indent_style: str = "spaces",
    indent_width: int = 4,
    strip_hidden: bool = True,
    remove_dead_imports: bool = True,
) -> ChangeSet:
    cs = ChangeSet()
    for f in files:
        original = read_text(f)
        updated = _normalize_newlines(original)
        if strip_hidden:
            updated = _strip_hidden(updated)
        if remove_dead_imports:
            updated = _remove_dead_imports_in_module(updated)
        # Note: indentation normalization is intentionally conservative in prototype
        if updated != original:
            cs.add(f, original, updated)
    return cs


