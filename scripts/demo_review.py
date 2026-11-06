"""Show inspection, optimization and an Excel-to-YAML preview on a temporary copy."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = "Completed-order revenue per customer, reviewed in Excel."


def snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def run_cli(project, *arguments):
    before = snapshot(project)
    print("\n$ extra " + shlex.join(["--project-dir", str(project), "--dialect", "duckdb", *arguments]), flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "dbt_extra", "--project-dir", str(project), "--dialect", "duckdb", *arguments],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)
    result.check_returncode()
    if (arguments[0] == "inspect" or "--preview" in arguments) and snapshot(project) != before:
        raise RuntimeError("A read-only demo command changed files")


def edit_description(workbook):
    book = load_workbook(workbook)
    try:
        edited = 0
        for sheet in book:
            headers = [cell.value for cell in sheet[1]]
            if not {"Type", "Name", "Description"} <= set(headers):
                continue
            for row in sheet.iter_rows(min_row=2):
                if (row[headers.index("Type")].value == "TABLE"
                        and row[headers.index("Name")].value == "customer_revenue"):
                    cell = row[headers.index("Description")]
                    if cell.protection.locked:
                        raise RuntimeError("The review description is not editable")
                    cell.value = DESCRIPTION
                    edited += 1
        if edited != 1:
            raise RuntimeError(f"Expected one customer_revenue TABLE row, found {edited}")
        book.save(workbook)
    finally:
        book.close()


def demo(project):
    original = snapshot(project)
    print("1/5 - Follow customer_name through three models, without simplification", flush=True)
    run_cli(project, "inspect", "customer_profile", "--columns", "customer_name", "--optimize", "false")

    print("\n2/5 - Show the simplified column logic (read-only)", flush=True)
    run_cli(project, "inspect", "customer_profile", "--columns", "customer_name")

    print("\n3/5 - Preview rewrites to an authored SQL model", flush=True)
    run_cli(project, "optimize", "--select", "gld_optimizer_projections", "--preview")

    print("\n4/5 - Export Excel and edit one supported description cell", flush=True)
    run_cli(project, "export", "--format", "xlsx", "--select", "customer_revenue")
    edit_description(project / "extra/review/review.xlsx")
    print(f"Set customer_revenue TABLE Description to: {DESCRIPTION}", flush=True)

    print("\n5/5 - Preview the original YAML change, without applying it", flush=True)
    run_cli(project, "import", str(project / "extra/review/review.xlsx"), "--preview")

    after = snapshot(project)
    if any(after.get(path) != content for path, content in original.items()):
        raise RuntimeError("The demo changed an original project file")
    print("\nAll original project files are unchanged. No dbt or SQL execution was performed.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temp-dir", type=Path, help="Parent for the disposable demo directory")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="dbt-extra-demo-", dir=args.temp_dir) as directory:
        project = Path(directory) / "jaffle_shop"
        shutil.copytree(
            ROOT / "examples/jaffle_shop", project,
            ignore=shutil.ignore_patterns("target", "logs", "extra", "dbt_packages", "__pycache__"),
        )
        demo(project)
    print("Temporary demo files removed.")


if __name__ == "__main__":
    main()
