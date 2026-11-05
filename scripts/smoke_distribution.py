"""Check built archives and exercise an isolated installed CLI, without dbt."""

import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def check_archives():
    version = importlib.metadata.version("dbt-extra")
    wheel = ROOT / "dist" / f"dbt_extra-{version}-py3-none-any.whl"
    source = ROOT / "dist" / f"dbt_extra-{version}.tar.gz"
    license_text = (ROOT / "LICENSE").read_bytes()
    with zipfile.ZipFile(wheel) as archive:
        metadata = archive.read(f"dbt_extra-{version}.dist-info/METADATA").decode()
        assert "License-Expression: MIT\n" in metadata
        assert "License-File: LICENSE\n" in metadata
        assert "Name: dbt-extra\n" in metadata
        assert f"Version: {version}\n" in metadata
        entries = archive.read(f"dbt_extra-{version}.dist-info/entry_points.txt").decode()
        assert "extra = dbt_extra.cli:cli" in entries
        assert "slbt =" not in entries
        assert archive.read(f"dbt_extra-{version}.dist-info/licenses/LICENSE") == license_text
        names = set(archive.namelist())
        for package in ("project", "sql", "analysis", "review", "files"):
            assert f"dbt_extra/{package}/__init__.py" in names
        assert not any(name.startswith(("dbt_extra/native/", "dbt_extra/compiler/", "dbt_extra/definitions/", "dbt_extra/catalog/")) for name in names)
        assert "dbt_extra/_legacy_cli.py" not in names
    with tarfile.open(source) as archive:
        prefix = f"dbt_extra-{version}/"
        names = set(archive.getnames())
        metadata = archive.extractfile(prefix + "PKG-INFO").read().decode()
        assert "License-Expression: MIT\n" in metadata
        assert "License-File: LICENSE\n" in metadata
        for path in (
            "LICENSE", "README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md",
            "pyproject.toml", "uv.lock", "docs/index.md", "tests/test_documentation.py",
            "scripts/smoke_distribution.py", "examples/jaffle_shop/extra_project.yaml",
            "examples/jaffle_shop/dbt_project.yml", "examples/jaffle_shop/profiles.yml",
            "examples/jaffle_shop/models/gld/customer_revenue.sql", "tests/workflows/test_dbt.py",
            "examples/jaffle_shop/models/gld/gld_orders.sql",
            "examples/jaffle_shop/models/brz/sources.yml",
            "examples/jaffle_shop/macros/round_money.sql",
            "examples/jaffle_shop/snapshots/slv/customer_history.sql",
            "examples/jaffle_shop/seeds/LICENSE",
            "examples/jaffle_shop/seeds/README.md",
            "examples/jaffle_shop/seeds/raw_customers.csv",
            "examples/jaffle_shop/seeds/raw_orders.csv",
            "examples/jaffle_shop/seeds/raw_payments.csv",
            "examples/jaffle_shop/seeds/demo_raw_orders.csv",
            "examples/jaffle_shop/tests/jaffle_shop_reconciliation.sql",
            "examples/jaffle_shop/tests/demo_revenue_reconciliation.sql",
            "docs/logo.md", "tests/test_branding.py",
            "tests/test_logo.py", "docs/assets/dbt-extra-mark.svg",
            "docs/assets/dbt-extra-mark-dark.svg", "docs/assets/dbt-extra-mark-mono.svg",
        ):
            assert prefix + path in names, f"sdist missing {path}"
        assert archive.extractfile(prefix + "LICENSE").read() == license_text
        assert not any(
            part in {".venv", "target", "logs", "__pycache__"} or part.endswith((".duckdb", ".duckdb.wal"))
            for name in names for part in Path(name).parts
        ), "sdist includes local build/runtime artifacts"
        assert not any(name.startswith(prefix + "examples/dbt_shop/") for name in names)
        for category in ("dbt", "catalog", "demo", "extra"):
            assert not any(name.startswith(prefix + f"examples/jaffle_shop/{category}/") for name in names)
    return version


def smoke_cli(version):
    with tempfile.TemporaryDirectory(prefix="extra-package-smoke-") as directory:
        environment = {k: v for k, v in os.environ.items() if k.casefold() != "extra_project_dir"}
        executable = Path(sys.executable).parent / ("extra.exe" if os.name == "nt" else "extra")
        assert executable.is_file(), f"Missing installed console command: {executable}"
        result = subprocess.run([str(executable), "--version"], cwd=directory,
                                text=True, capture_output=True, check=True, env=environment)
        assert result.stdout.strip() == f"extra, version {version}"
        def run(*arguments):
            result = subprocess.run(
                [sys.executable, "-I", "-m", "dbt_extra", *arguments], cwd=directory,
                text=True, capture_output=True, env=environment,
            )
            print(result.stdout.strip())
            if result.returncode:
                print(result.stderr, file=sys.stderr)
                result.check_returncode()
            return result.stdout

        assert version in run("--version")
        project = Path(directory) / "project"
        (project / "models").mkdir(parents=True)
        (project / "dbt_project.yml").write_text("name: smoke\nversion: '1.0'\n", encoding="utf-8")
        (project / "models/example.sql").write_text("select 1 + 0 as id\n", encoding="utf-8")
        run("--project-dir", "project", "--dialect", "duckdb", "init")
        run("--project-dir", "project", "validate")
        run("--project-dir", "project", "inspect", "example", "--columns", "id")
        run("--project-dir", "project", "optimize", "--preview")
        run("--project-dir", "project", "export", "--format", "json")
        catalog = json.loads((project / "extra/review/review.json").read_text(encoding="utf-8"))
        assert (catalog["format_version"], catalog["source_of_truth"]) == (1, "dbt")
        assert "format" not in catalog
        assert catalog["resources"][0]["name"] == "example"
        run("--project-dir", "project", "export", "--format", "xlsx")
        run("--project-dir", "project", "import", str(project / "extra/review/review.xlsx"), "--preview")


if __name__ == "__main__":
    smoke_cli(check_archives())
    print("Distribution checks passed")
