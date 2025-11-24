from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

import libcst as cst
from libcst.metadata import PositionProvider

from .diff_utils import ChangeSet
from .project import read_text


@dataclass
class ExtractError(Exception):
    message: str


def _gather_statements_by_line(mod: cst.Module, func_name: str) -> Tuple[cst.FunctionDef, List[Tuple[int, int, cst.CSTNode]]]:
    wrapper = cst.MetadataWrapper(mod)
    positions = wrapper.resolve(PositionProvider)
    wmod = wrapper.module
    fn: Optional[cst.FunctionDef] = None
    for node in wmod.body:
        if isinstance(node, cst.FunctionDef) and node.name.value == func_name:
            fn = node
            break
    if not fn:
        raise ExtractError("Function not found")
    stmt_positions: List[Tuple[int, int, cst.CSTNode]] = []
    for stmt in fn.body.body:
        try:
            start, end = stmt.get_lines()
        except Exception:
            try:
                pos = positions[stmt]
                start, end = pos.start.line, pos.end.line
            except Exception:
                continue
        stmt_positions.append((start, end, stmt))
    return fn, stmt_positions


def _collect_names_used(node: cst.CSTNode) -> Set[str]:
    used: Set[str] = set()

    class V(cst.CSTVisitor):
        def visit_Name(self, n: cst.Name) -> Optional[bool]:
            used.add(n.value)
            return None

    node.visit(V())
    return used


def _collect_assigned_in_block(node: cst.CSTNode) -> Set[str]:
    assigned: Set[str] = set()

    class V(cst.CSTVisitor):
        def visit_AssignTarget(self, n: cst.AssignTarget) -> Optional[bool]:
            if isinstance(n.target, cst.Name):
                assigned.add(n.target.value)
            return None

        def visit_AugAssign(self, n: cst.AugAssign) -> Optional[bool]:
            if isinstance(n.target, cst.Name):
                assigned.add(n.target.value)
            return None

        def visit_For(self, n: cst.For) -> Optional[bool]:
            if isinstance(n.target, cst.Name):
                assigned.add(n.target.value)
            return None

        def visit_With(self, n: cst.With) -> Optional[bool]:
            for item in n.items:
                if item.asname and isinstance(item.asname.name, cst.Name):
                    assigned.add(item.asname.name.value)
            return None

    node.visit(V())
    return assigned


def _contains_ambiguous_control_flow(node: cst.CSTNode) -> bool:
    blocked = False

    class V(cst.CSTVisitor):
        def visit_Return(self, n: cst.Return) -> Optional[bool]:
            nonlocal blocked
            blocked = True
            return None

        def visit_Break(self, n: cst.Break) -> Optional[bool]:
            nonlocal blocked
            blocked = True
            return None

        def visit_Continue(self, n: cst.Continue) -> Optional[bool]:
            nonlocal blocked
            blocked = True
            return None

        def visit_Raise(self, n: cst.Raise) -> Optional[bool]:
            nonlocal blocked
            blocked = True
            return None

        def visit_Yield(self, n: cst.Yield) -> Optional[bool]:
            nonlocal blocked
            blocked = True
            return None

    node.visit(V())
    return blocked


def extract_function(
    file_path: Path,
    function_name: str,
    start_line: int,
    end_line: int,
    new_name: str,
    return_variable: Optional[str] = None,
) -> ChangeSet:
    text = read_text(file_path)
    mod = cst.parse_module(text)

    # Build metadata wrapper for positions, but keep editing the original mod tree
    wrapper = cst.MetadataWrapper(mod)
    positions = wrapper.resolve(PositionProvider)
    wmod = wrapper.module

    # Find function in both wrapper tree and base tree
    w_fn: Optional[cst.FunctionDef] = None
    for node in wmod.body:
        if isinstance(node, cst.FunctionDef) and node.name.value == function_name:
            w_fn = node
            break
    if not w_fn:
        raise ExtractError("Function not found")

    base_fn: Optional[cst.FunctionDef] = None
    base_fn_index: Optional[int] = None
    for i, node in enumerate(mod.body):
        if isinstance(node, cst.FunctionDef) and node.name.value == function_name:
            base_fn = node
            base_fn_index = i
            break
    if not base_fn or base_fn_index is None:
        raise ExtractError("Function not found in base module")

    # Map wrapper statements to indices and line ranges
    w_body = list(w_fn.body.body)
    stmt_positions: List[Tuple[int, int, int]] = []  # (start, end, index)
    for idx, stmt in enumerate(w_body):
        try:
            start, end = stmt.get_lines()
        except Exception:
            try:
                pos = positions[stmt]
                start, end = pos.start.line, pos.end.line
            except Exception:
                continue
        stmt_positions.append((start, end, idx))

    # Select indices by line range
    selected_indices: List[int] = []
    for s_line, e_line, idx in stmt_positions:
        if s_line >= start_line and e_line <= end_line:
            selected_indices.append(idx)
    if not selected_indices:
        raise ExtractError("No complete statements found in the given range")
    if selected_indices != list(range(min(selected_indices), max(selected_indices) + 1)):
        raise ExtractError("Selected lines do not form a contiguous block")

    # Analyze names on wrapper nodes for convenience
    selected_w_nodes = [w_body[i] for i in selected_indices]
    block = cst.Module(body=selected_w_nodes)
    used = _collect_names_used(block)
    assigned = _collect_assigned_in_block(block)

    # Base function body nodes (we will edit these)
    base_body = list(base_fn.body.body)

    # Params from base function
    params = {p.name.value for p in base_fn.params.params}
    params |= {p.name.value for p in base_fn.params.kwonly_params}

    # Prior assignments before the block in base tree
    before_block = cst.Module(body=base_body[: min(selected_indices)])
    assigned_before = _collect_assigned_in_block(before_block)
    free_vars = sorted([n for n in used if n not in assigned and (n in params or n in assigned_before)])

    # Determine escaping assignments by checking usage later in base tree
    following = cst.Module(body=base_body[max(selected_indices) + 1 :])
    used_later = _collect_names_used(following)
    escaping = sorted([n for n in assigned if n in used_later])

    if _contains_ambiguous_control_flow(block):
        raise ExtractError("Ambiguous control flow detected in selected block; aborting")
    if len(escaping) > 1 and not return_variable:
        raise ExtractError("Multiple values escape the block; specify --return-var or select a simpler range")

    # Build extracted function (based on base tree nodes)
    params_list = [cst.Param(name=cst.Name(n)) for n in free_vars]
    new_body_nodes = [n for n in base_body[min(selected_indices) : max(selected_indices) + 1]]
    ret_name: Optional[str] = return_variable or (escaping[0] if escaping else None)
    if ret_name:
        new_body_nodes.append(cst.SimpleStatementLine([cst.Return(value=cst.Name(ret_name))]))
    new_func = cst.FunctionDef(
        name=cst.Name(new_name),
        params=cst.Parameters(params=params_list),
        body=cst.IndentedBlock(body=new_body_nodes),
    )

    # Call site to replace the block
    call_args = [cst.Arg(value=cst.Name(n)) for n in free_vars]
    call_expr: cst.BaseExpression = cst.Call(func=cst.Name(new_name), args=call_args)
    if ret_name:
        call_stmt: cst.CSTNode = cst.SimpleStatementLine(
            [cst.Assign(targets=[cst.AssignTarget(target=cst.Name(ret_name))], value=call_expr)]
        )
    else:
        call_stmt = cst.SimpleStatementLine([cst.Expr(value=call_expr)])

    # Replace block in base function
    new_base_fn_body = base_body[: min(selected_indices)] + [call_stmt] + base_body[max(selected_indices) + 1 :]
    new_base_fn = base_fn.with_changes(body=cst.IndentedBlock(body=new_base_fn_body))

    # Construct new module body: replace base function by name match and append new function after it
    new_module_body: List[cst.CSTNode] = []
    inserted = False
    # If a function with new_name already exists at module level, reuse it (do not insert another definition)
    new_func_exists = any(isinstance(node, cst.FunctionDef) and node.name.value == new_name for node in mod.body)
    for node in mod.body:
        if isinstance(node, cst.FunctionDef) and node.name.value == function_name and not inserted:
            new_module_body.append(new_base_fn)
            if not new_func_exists:
                new_module_body.append(new_func)
            inserted = True
        else:
            new_module_body.append(node)
    if not inserted:
        raise ExtractError("Failed to reconstruct function body")

    new_mod = mod.with_changes(body=new_module_body)
    cs = ChangeSet()
    cs.add(file_path, text, new_mod.code)
    return cs


