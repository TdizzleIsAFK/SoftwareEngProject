from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table

from .project import discover_python_files
from .diff_utils import ChangeSet
from . import analyze as analyze_mod
from . import rename as rename_mod
from . import extract as extract_mod
from . import readability as readability_mod


app = typer.Typer(add_completion=False, help="Python refactoring tool (prototype)")
console = Console()


def _split_patterns(pats: Optional[str]) -> List[str]:
    if not pats:
        return []
    return [p.strip() for p in pats.split(",") if p.strip()]


@app.command()
def analyze(
    root: str = typer.Argument(".", help="Project root directory"),
    include: Optional[str] = typer.Option(None, help="Comma-separated include globs"),
    exclude: Optional[str] = typer.Option(None, help="Comma-separated exclude globs"),
    json_out: bool = typer.Option(False, "--json", help="Print JSON output"),
):
    """Analyze codebase metrics and potential issues."""
    root_path = Path(root).resolve()
    files = list(discover_python_files(root_path, _split_patterns(include), _split_patterns(exclude)))
    report = analyze_mod.analyze_project(root_path, files)
    if json_out:
        console.print_json(data=report)
        return
    table = Table(title="Analysis Report")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Files", str(report["files"]))
    table.add_row("Lines", str(report["lines"]))
    table.add_row("Functions", str(report["functions"]))
    table.add_row("Classes", str(report["classes"]))
    table.add_row("Potential dead imports", str(len(report["potential_dead_imports"])) )
    console.print(table)


@app.command()
def rename(
    file: Optional[str] = typer.Option(None, help="Path to defining file for the symbol"),
    name: str = typer.Option(..., help="Old symbol name to rename"),
    to: str = typer.Option(..., help="New symbol name"),
    function: Optional[str] = typer.Option(None, help="Limit variable rename to inside this function"),
    klass: Optional[str] = typer.Option(None, "--class", help="Limit variable rename to inside this class"),
    root: str = typer.Option(".", help="Project root"),
    include: Optional[str] = typer.Option(None, help="Comma-separated include globs"),
    exclude: Optional[str] = typer.Option(None, help="Comma-separated exclude globs"),
    preview: bool = typer.Option(False, help="Show diffs without writing"),
    apply: bool = typer.Option(False, help="Write changes to disk"),
):
    """Safely rename variables/functions/classes.

    For project-wide rename of a top-level function/class, provide --file of the defining module.
    For local variable rename, provide --file and optionally --function/--class to narrow scope.
    """
    if not preview and not apply:
        console.print("[yellow]No action selected. Use --preview or --apply.[/yellow]")
        raise typer.Exit(code=2)

    root_path = Path(root).resolve()
    files = list(discover_python_files(root_path, _split_patterns(include), _split_patterns(exclude)))

    change_set: ChangeSet = rename_mod.rename_entrypoint(
        root_path=root_path,
        files=files,
        file_path=Path(file).resolve() if file else None,
        symbol_name=name,
        new_name=to,
        function_name=function,
        class_name=klass,
    )

    if preview:
        change_set.preview(console)
    if apply:
        change_set.apply(console)


@app.command()
def extract(
    file: str = typer.Option(..., help="Path to file containing the function"),
    function: str = typer.Option(..., help="Function name containing the block to extract"),
    start_line: int = typer.Option(..., help="Start line (1-based) of the block to extract"),
    end_line: int = typer.Option(..., help="End line (inclusive) of the block to extract"),
    new_name: str = typer.Option(..., help="New helper function name"),
    return_var: Optional[str] = typer.Option(None, help="Optional variable name to capture returned value"),
    root: str = typer.Option(".", help="Project root"),
    preview: bool = typer.Option(False, help="Show diffs without writing"),
    apply: bool = typer.Option(False, help="Write changes to disk"),
):
    """Extract a contiguous block of code into a new function and update the call site."""
    if not preview and not apply:
        console.print("[yellow]No action selected. Use --preview or --apply.[/yellow]")
        raise typer.Exit(code=2)

    change_set = extract_mod.extract_function(
        file_path=Path(file).resolve(),
        function_name=function,
        start_line=start_line,
        end_line=end_line,
        new_name=new_name,
        return_variable=return_var,
    )
    if preview:
        change_set.preview(console)
    if apply:
        change_set.apply(console)


@app.command(name="tidy")
def tidy_command(
    root: str = typer.Argument(".", help="Project root"),
    include: Optional[str] = typer.Option(None, help="Comma-separated include globs"),
    exclude: Optional[str] = typer.Option(None, help="Comma-separated exclude globs"),
    indent_style: str = typer.Option("spaces", help="spaces|tabs"),
    indent_width: int = typer.Option(4, help="Indent width when using spaces"),
    strip_hidden: bool = typer.Option(True, help="Remove zero-width chars and normalize newlines"),
    remove_dead_imports: bool = typer.Option(True, help="Remove imports that are not used in the module"),
    preview: bool = typer.Option(False, help="Show diffs without writing"),
    apply: bool = typer.Option(False, help="Write changes to disk"),
):
    """Apply readability and hygiene transforms to files."""
    if not preview and not apply:
        console.print("[yellow]No action selected. Use --preview or --apply.[/yellow]")
        raise typer.Exit(code=2)

    root_path = Path(root).resolve()
    files = list(discover_python_files(root_path, _split_patterns(include), _split_patterns(exclude)))
    change_set = readability_mod.tidy_files(
        files,
        indent_style=indent_style,
        indent_width=indent_width,
        strip_hidden=strip_hidden,
        remove_dead_imports=remove_dead_imports,
    )
    if preview:
        change_set.preview(console)
    if apply:
        change_set.apply(console)


@app.command()
def spec(
    sample_root: str = typer.Argument("examples/sample_project", help="Path to sample project root"),
    verbose: bool = typer.Option(False, help="Show verbose pytest output"),
):
    """Run the built-in spec: perform a rename and extract in the sample project and run tests."""
    result = analyze_mod.run_spec_and_tests(Path(sample_root).resolve(), verbose=verbose)
    console.print_json(data=result)


def main() -> None:
    app()


if __name__ == "__main__":
    main()


