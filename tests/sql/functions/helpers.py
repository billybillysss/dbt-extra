"""Shared contracts; each dialect collects its own parameterized test cases."""

from pathlib import Path

import pytest
from sqlglot import exp, parse_one

from dbt_extra.analysis import analyze
from dbt_extra.analysis.type_inference import inferred_types
from dbt_extra.enrichment import enrich
from dbt_extra.errors import SpecError
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.project import Project
from dbt_extra.sql.functions import function_shape, function_spec
from dbt_extra.sql.rewrites.structural import plain_queries, pushdown_safe_predicates
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.safety import has_evaluation_barrier
from tests.helpers import put, snapshot


ROOT = Path(__file__).resolve().parents[3]


def recognition(dialect, spec):
    # Native SQLGlot functions may not inflate the local gap count. A dependency
    # upgrade gaining recognition intentionally requires review of this catalog.
    raw = parse_one("SELECT " + spec.example, read=dialect).selects[0]
    assert isinstance(raw, exp.Anonymous), (spec.name, type(raw).__name__)
    parsed = parse_authored("SELECT " + spec.example + " AS result", dialect).tree
    node = parsed.selects[0].this
    assert function_spec(node) == spec
    assert function_spec(node.copy()) == spec
    assert function_shape(node).kind == spec.kind
    assert function_spec(parse_authored("SELECT " + spec.name.upper() + "(" + ",".join("1" for _ in raw.expressions) + ")", dialect).tree.selects[0]) == spec
    rendered = parsed.sql(dialect=dialect)
    reparsed = parse_authored(rendered, dialect).tree
    # Spark's typed date literals render as CAST and reparse as TryCast. Check
    # stable SQL plus semantic recognition, not equality of those native nodes.
    assert reparsed.sql(dialect=dialect) == rendered
    assert function_spec(reparsed.selects[0].this) == spec
    # Qualification must never silently turn a schema-qualified UDF into a builtin.
    udf = exp.Dot(this=exp.to_identifier("udf"), expression=node.copy())
    assert function_spec(udf.expression) is None
    quoted = node.copy()
    quoted.set("this", exp.to_identifier(spec.name, quoted=True))
    assert function_spec(quoted) is None
    for count in {spec.minimum - 1, (spec.maximum + 1) if spec.maximum is not None else -1}:
        if count >= 0:
            invalid = node.copy()
            invalid.set("expressions", [exp.Literal.number(1) for _ in range(count)])
            assert function_spec(invalid) is None


def typing(dialect, spec):
    tree = parse_authored("SELECT " + spec.example + " AS result FROM t", dialect).tree
    before = tree.dump()
    actual = inferred_types(tree, {"t": {"id": "BIGINT"}}, dialect)
    expected = {"result": exp.DataType.build(spec.returns, dialect=dialect).sql(dialect=dialect)} if spec.returns else {}
    assert actual == expected
    assert tree.dump() == before  # Inference is not an authored-AST mutation.
    if spec.returns:
        nested = parse_authored("SELECT COALESCE(" + spec.example + ", NULL) AS result FROM t", dialect).tree
        baseline = parse_authored("SELECT COALESCE(CAST(NULL AS " + spec.returns + "), NULL) AS result FROM t", dialect).tree
        # SQLGlot-native coercion can widen even COALESCE(SMALLINT, NULL) in
        # Spark. Assert integration without claiming to fix native coercion.
        assert inferred_types(nested, {"t": {"id": "BIGINT"}}, dialect) == inferred_types(baseline, {"t": {"id": "BIGINT"}}, dialect)


def safety(dialect, spec):
    code = "WITH base AS (SELECT " + spec.example + " AS result FROM t) SELECT result FROM base"
    tree = parse_authored(code, dialect).tree
    assert has_evaluation_barrier(tree), "Recognition alone must not authorize dropping/reordering evaluation"
    outcomes = []
    result = parse_authored(optimize_source(code, dialect, schema={"t": {"id": "BIGINT"}}, outcomes=outcomes), dialect).tree
    def calls(query):
        return [n.transform(lambda c: exp.Column(this=c.this.copy()) if isinstance(c, exp.Column) else c).sql(dialect=dialect)
                for n in query.find_all(exp.Anonymous)]

    before, after = calls(tree), calls(result)
    assert after == before, "Opaque evaluations must not be erased, duplicated or rewritten"
    assert any(i["status"] == "blocked" for i in outcomes)
    if spec.kind in {"aggregate", "generator", "window"}:
        assert not plain_queries(tree, aggregates=True)
        assert pushdown_safe_predicates(tree.copy(), dialect) == tree


def enrichment(native, dialect, spec):
    put(native, "models/function_example.sql", "SELECT " + spec.example + " AS result FROM {{ ref('orders') }}")
    yaml = put(native, "models/function_example.yml", "version: 2\nmodels:\n  - name: function_example\n")
    project = Project(native, dialect=dialect)
    before = snapshot(native)
    analysis = analyze(project, project.find_model("function_example"))
    expected = exp.DataType.build(spec.returns, dialect=dialect).sql(dialect=dialect) if spec.returns else None
    column = next((c for c in analysis["columns"] if c["name"] == "result"), {})
    assert column.get("inferred_type") == expected, analysis
    changes, report = enrich(project, select=["function_example"])
    assert snapshot(native) == before
    assert not any(r.get("value") for r in report if r["property"] == "description")
    if expected:
        assert set(changes.changed()) == {yaml}
        changes.apply()
        assert Project(native, dialect=dialect).find_model("function_example").columns["result"]["data_type"] == expected
    else:
        assert not changes.changed()


def documentation(dialect, functions):
    text = (ROOT / f"docs/reference/sql-functions/{dialect}.md").read_text(encoding="utf-8")
    rows = [line.split(" | ") for line in text.splitlines() if line.startswith("| `")]
    assert len(rows) == len(functions)
    for row, spec in zip(rows, functions):
        assert row[0] == "| `" + spec.name + "`"
        assert row[1] == spec.kind
        assert row[2] == ("`" + spec.returns + "`" if spec.returns else "unresolved / input-dependent")
        assert row[3] == spec.volatility + " |"
