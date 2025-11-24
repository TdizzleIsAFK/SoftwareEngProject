from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import libcst as cst
from libcst.metadata import PositionProvider

from .project import read_text
from .readability import find_potential_dead_imports
from .diff_utils import ChangeSet
import shutil
import tempfile
import subprocess
import os


def analyze_project(root: Path, files: List[Path]) -> Dict:
    total_lines = 0
    functions = 0
    classes = 0
    potential_dead_imports: List[Tuple[str, int, str]] = []
    for f in files:
        text = read_text(f)
        total_lines += text.count("\n") + 1 if text else 0
        try:
            mod = cst.parse_module(text)
        except Exception:
            continue
        for node in mod.body:
            if isinstance(node, cst.FunctionDef):
                functions += 1
            elif isinstance(node, cst.ClassDef):
                classes += 1
        potential_dead_imports.extend(find_potential_dead_imports(f, text))
    return {
        "files": len(files),
        "lines": total_lines,
        "functions": functions,
        "classes": classes,
        "potential_dead_imports": potential_dead_imports,
    }


def run_spec_and_tests(sample_root: Path, verbose: bool = False) -> Dict:
    # Work in a temporary copy to avoid altering the original sample project
    tmp_dir = Path(tempfile.mkdtemp(prefix="refactor_spec_"))
    workdir = tmp_dir / "project"
    shutil.copytree(sample_root, workdir)

    # Run baseline tests
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(workdir) + (os.pathsep + existing_pp if existing_pp else "")

    base_rc = subprocess.call(
        [
            "pytest",
            "-q" if not verbose else "-vv",
            str(workdir / "tests"),
        ],
        cwd=str(workdir),
        env=env,
    )

    # Perform a simple rename and extract for the sample project
    from . import rename as rename_mod
    from . import extract as extract_mod
    from .project import discover_python_files

    files = list(discover_python_files(workdir, ["**/*.py"], []))

    # rename: sample utils function "dup_block" -> "extracted_helper"
    change_set = rename_mod.rename_entrypoint(
        root_path=workdir,
        files=files,
        file_path=workdir / "sample" / "utils.py",
        symbol_name="dup_block",
        new_name="extracted_helper",
        function_name=None,
        class_name=None,
    )
    change_set.apply(None)

    # extract a block from process_data in main.py
    # Find the exact statement range for the loop block in sample/main.py by scanning lines
    # We know the duplicate sum loop appears after cleaning and before avg assignment
    main_text = (workdir / "sample" / "main.py").read_text(encoding="utf-8")
    lines = main_text.splitlines()
    loop_start = None
    loop_end = None
    for i, line in enumerate(lines, start=1):
        if loop_start is None and line.strip().startswith("total = 0"):
            loop_start = i
        if loop_start is not None and line.strip().startswith("avg ="):
            loop_end = i - 1
            break
    if loop_start is None or loop_end is None:
        loop_start, loop_end = 10, 15  # fallback

    cs2 = extract_mod.extract_function(
        file_path=workdir / "sample" / "main.py",
        function_name="process_data",
        start_line=loop_start,
        end_line=loop_end,
        new_name="compute_total",
        return_variable="total",
    )
    cs2.apply(None)

    # Run tests again
    post_rc = subprocess.call(
        [
            "pytest",
            "-q" if not verbose else "-vv",
            str(workdir / "tests"),
        ],
        cwd=str(workdir),
        env=env,
    )

    return {
        "baseline_tests_passed": base_rc == 0,
        "post_refactor_tests_passed": post_rc == 0,
        "tmp_project": str(workdir),
    }


