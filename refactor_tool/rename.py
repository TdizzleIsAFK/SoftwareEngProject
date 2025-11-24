from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

import libcst as cst
from libcst import matchers as m
from libcst.metadata import PositionProvider, ParentNodeProvider

from .diff_utils import ChangeSet
from .project import module_path_from_file, read_text


@dataclass
class RenameError(Exception):
    message: str


def _update_docstrings_and_type_strings(text: str, old: str, new: str) -> str:
    # Simple word-boundary replace for docstrings and forward refs
    import re
    pattern = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)")
    return pattern.sub(new, text)


def _has_top_level_definition(mod: cst.Module, name: str) -> bool:
    for stmt in mod.body:
        if isinstance(stmt, (cst.FunctionDef, cst.ClassDef)) and stmt.name.value == name:
            return True
    return False


class LocalVarRenamer(cst.CSTTransformer):
    def __init__(self, target_function: str, target_class: Optional[str], old: str, new: str) -> None:
        self.target_function = target_function
        self.target_class = target_class
        self.old = old
        self.new = new
        self._in_class = False
        self._in_function = False

    def visit_ClassDef(self, node: cst.ClassDef) -> Optional[bool]:
        if self.target_class and node.name.value == self.target_class:
            self._in_class = True
        return None

    def leave_ClassDef(self, node: cst.ClassDef, updated: cst.ClassDef) -> cst.CSTNode:
        if self.target_class and node.name.value == self.target_class:
            self._in_class = False
        return updated

    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        if (not self.target_class or self._in_class) and node.name.value == self.target_function:
            self._in_function = True
        return None

    def leave_FunctionDef(self, node: cst.FunctionDef, updated: cst.FunctionDef) -> cst.CSTNode:
        if (not self.target_class or self._in_class) and node.name.value == self.target_function:
            self._in_function = False
        return updated

    def leave_Name(self, node: cst.Name, updated: cst.Name) -> cst.CSTNode:
        if self._in_function and node.value == self.old:
            return updated.with_changes(value=self.new)
        return updated


def _collect_assigned_names(func: cst.FunctionDef) -> Set[str]:
    assigned: Set[str] = set()

    class AssignVisitor(cst.CSTVisitor):
        def visit_Param(self, node: cst.Param) -> Optional[bool]:
            assigned.add(node.name.value)
            return None

        def visit_AssignTarget(self, node: cst.AssignTarget) -> Optional[bool]:
            target = node.target
            if isinstance(target, cst.Name):
                assigned.add(target.value)
            return None

        def visit_AugAssign(self, node: cst.AugAssign) -> Optional[bool]:
            if isinstance(node.target, cst.Name):
                assigned.add(node.target.value)
            return None

        def visit_For(self, node: cst.For) -> Optional[bool]:
            if isinstance(node.target, cst.Name):
                assigned.add(node.target.value)
            return None

        def visit_With(self, node: cst.With) -> Optional[bool]:
            for item in node.items:
                if item.asname and isinstance(item.asname.name, cst.Name):
                    assigned.add(item.asname.name.value)
            return None

    func.visit(AssignVisitor())
    return assigned


def _find_function(mod: cst.Module, function_name: str, class_name: Optional[str]) -> Optional[cst.FunctionDef]:
    if class_name:
        for stmt in mod.body:
            if isinstance(stmt, cst.ClassDef) and stmt.name.value == class_name:
                for elem in stmt.body.body:
                    if isinstance(elem, cst.FunctionDef) and elem.name.value == function_name:
                        return elem
        return None
    else:
        for stmt in mod.body:
            if isinstance(stmt, cst.FunctionDef) and stmt.name.value == function_name:
                return stmt
        return None


def _dotted_name_from_node(node: cst.CSTNode) -> Optional[str]:
    # Convert Name or Attribute to 'a.b.c' string
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        left = _dotted_name_from_node(node.value)
        right = node.attr.value if isinstance(node.attr, cst.Name) else None
        if left and right:
            return f"{left}.{right}"
        return left or right
    return None


def rename_entrypoint(
    root_path: Path,
    files: List[Path],
    file_path: Optional[Path],
    symbol_name: str,
    new_name: str,
    function_name: Optional[str],
    class_name: Optional[str],
) -> ChangeSet:
    """Entry point for rename operations.

    - If function_name is provided: local variable rename inside that function in the given file_path.
    - Else if file_path is provided: rename a top-level function or class across project.
    """
    if symbol_name == new_name:
        raise RenameError("Old and new names are identical.")

    changes = ChangeSet()

    if function_name:
        if not file_path:
            raise RenameError("--file is required for local variable rename.")
        text = read_text(file_path)
        mod = cst.parse_module(text)
        func = _find_function(mod, function_name, class_name)
        if not func:
            raise RenameError("Target function not found.")
        # collision check
        assigned = _collect_assigned_names(func)
        if new_name in assigned and symbol_name != new_name:
            raise RenameError("Rename would shadow an existing symbol in the function scope.")
        transformer = LocalVarRenamer(function_name, class_name, symbol_name, new_name)
        new_mod = mod.visit(transformer)
        updated = _update_docstrings_and_type_strings(new_mod.code, symbol_name, new_name)
        changes.add(file_path, text, updated)
        return changes

    # project-wide top-level rename
    if not file_path:
        raise RenameError("--file is required to identify the defining module for project-wide rename.")

    defining_text = read_text(file_path)
    defining_mod = cst.parse_module(defining_text)
    # verify definition exists and type
    kind: Optional[str] = None
    for stmt in defining_mod.body:
        if isinstance(stmt, cst.FunctionDef) and stmt.name.value == symbol_name:
            kind = "function"
            break
        if isinstance(stmt, cst.ClassDef) and stmt.name.value == symbol_name:
            kind = "class"
            break
    if not kind:
        raise RenameError("Symbol not defined at top-level in the given file.")

    if _has_top_level_definition(defining_mod, new_name):
        raise RenameError("Rename would collide with an existing top-level definition in defining file.")

    # update defining file name and internal references
    class DefRename(cst.CSTTransformer):
        def leave_FunctionDef(self, node: cst.FunctionDef, updated: cst.FunctionDef) -> cst.CSTNode:
            if node.name.value == symbol_name:
                return updated.with_changes(name=cst.Name(new_name))
            return updated

        def leave_ClassDef(self, node: cst.ClassDef, updated: cst.ClassDef) -> cst.CSTNode:
            if node.name.value == symbol_name:
                return updated.with_changes(name=cst.Name(new_name))
            return updated

        def leave_Name(self, node: cst.Name, updated: cst.Name) -> cst.CSTNode:
            if node.value == symbol_name:
                return updated.with_changes(value=new_name)
            return updated

    new_def_mod = defining_mod.visit(DefRename())
    new_def_text = _update_docstrings_and_type_strings(new_def_mod.code, symbol_name, new_name)
    changes.add(file_path, defining_text, new_def_text)

    # compute module path
    module_path = module_path_from_file(root_path, file_path)

    # update other files' imports and attribute references
    for f in files:
        text = read_text(f)
        try:
            mod = cst.parse_module(text)
        except Exception:
            continue

        updated_mod = mod
        changed = False

        replaced_symbol_in_module = False

        class ImportRename(cst.CSTTransformer):
            def leave_ImportFrom(self, node: cst.ImportFrom, updated: cst.ImportFrom) -> cst.CSTNode:
                nonlocal changed
                nonlocal replaced_symbol_in_module
                # from module_path import symbol_name [as alias]
                module_str = _dotted_name_from_node(node.module) if node.module else None
                matches_module = False
                if module_path and module_str and node.names:
                    # match either fully qualified or last segment for simple/relative imports
                    last = module_path.split(".")[-1]
                    if module_str == module_path or module_str == last:
                        matches_module = True
                if matches_module:
                    new_names = []
                    modified_local = False
                    for n in node.names:
                        if isinstance(n.name, cst.Name) and n.name.value == symbol_name:
                            # replace the imported name
                            new_names.append(n.with_changes(name=cst.Name(new_name)))
                            modified_local = True
                        else:
                            new_names.append(n)
                    if modified_local:
                        changed = True
                        replaced_symbol_in_module = True
                        return updated.with_changes(names=tuple(new_names))
                return updated

            def leave_Import(self, node: cst.Import, updated: cst.Import) -> cst.CSTNode:
                # nothing to change in 'import module' here
                return updated

        updated_mod = updated_mod.visit(ImportRename())

        # If imported via 'import module', update attribute access module.old -> module.new
        # Build set of module aliases for module_path
        module_aliases: Set[str] = set()

        class ImportAliasCollector(cst.CSTVisitor):
            def visit_Import(self, node: cst.Import) -> Optional[bool]:
                for alias_node in node.names:
                    full = _dotted_name_from_node(alias_node.name)
                    if not full:
                        continue
                    alias_name = alias_node.asname.name.value if alias_node.asname else full.split(".")[-1]
                    if module_path and full == module_path:
                        module_aliases.add(alias_name)
                return None

        updated_mod.visit(ImportAliasCollector())

        if module_aliases:
            class AttrRename(cst.CSTTransformer):
                def leave_Attribute(self, node: cst.Attribute, updated: cst.Attribute) -> cst.CSTNode:
                    nonlocal changed
                    if isinstance(node.value, cst.Name) and node.value.value in module_aliases:
                        if isinstance(node.attr, cst.Name) and node.attr.value == symbol_name:
                            changed = True
                            return updated.with_changes(attr=cst.Name(new_name))
                    return updated

            updated_mod = updated_mod.visit(AttrRename())

        # If we replaced an imported symbol name, also rename bare Name uses
        if replaced_symbol_in_module:
            class BareNameRename(cst.CSTTransformer):
                def leave_Name(self, node: cst.Name, updated: cst.Name) -> cst.CSTNode:
                    nonlocal changed
                    if node.value == symbol_name:
                        changed = True
                        return updated.with_changes(value=new_name)
                    return updated

            updated_mod = updated_mod.visit(BareNameRename())

        if updated_mod.code != text:
            updated_text = _update_docstrings_and_type_strings(updated_mod.code, symbol_name, new_name)
            if updated_text != text:
                changes.add(f, text, updated_text)

    return changes


