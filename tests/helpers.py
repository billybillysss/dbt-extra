"""Shared dbt project fixtures and authored-file helpers."""

import csv
from pathlib import Path
import shutil

from click.testing import CliRunner
import pytest

from dbt_extra.cli import cli
from dbt_extra.project import Project


SQL_DIALECTS = ("duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql", "fabric",
                "databricks", "redshift", "trino", "athena")


def put(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")
    return target


@pytest.fixture
def native(tmp_path):
    put(tmp_path, "dbt_project.yml", "name: shop\nversion: '1.0'\nmodel-paths: [models]\nmodels:\n  shop:\n    +tags: [review]\n")
    put(tmp_path, "models/slv/orders.sql", "{{ config(materialized='view', tags=['slv']) }}\nselect id, amount from {{ source('raw', 'orders') }} where amount >= 0\n")
    put(tmp_path, "models/gld/revenue.sql", "{{ config(materialized='table') }}\nwith base as (select id, amount from {{ ref('orders') }})\nselect id, amount + 0 as revenue from base where amount > 1\n")
    put(tmp_path, "models/schema.yml", """# Keep this comment
version: 2
sources:
  - name: raw
    database: landing
    tables:
      - name: orders
        columns:
          - name: id
            description: Order identifier
            data_type: bigint
          - name: amount
            description: Order amount
            data_type: decimal(12,2)
models:
  - name: orders
    description: 'All valid orders' # preserve inline comment
    columns:
      - name: id
        data_type: bigint
        description: Order identifier
        data_tests: [not_null]
      - name: amount
        data_type: decimal(12,2)
        description: Order amount
  - name: revenue
    config:
      tags: [finance]
    columns:
      - name: id
      - name: revenue
""")
    return tmp_path


def project(root, **kwargs):
    return Project(root, dialect="duckdb", **kwargs)


def invoke(root, *args):
    return CliRunner().invoke(cli, ["--project-dir", str(root), "--dialect", "duckdb", *args])


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def optimizer_inputs(root):
    """Seed real-rule inputs in a temporary copy, not the mutable example tree."""
    for path in (Path(__file__).parent / "fixtures/optimization").glob("*.sql"):
        shutil.copyfile(path, root / "models/gld/optimization" / path.name)


def edit_csv(root, sheet, predicate, **values):
    path = root / f"{sheet}.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers, rows = reader.fieldnames, list(reader)
    for row in rows:
        if predicate(row):
            row.update(values)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
