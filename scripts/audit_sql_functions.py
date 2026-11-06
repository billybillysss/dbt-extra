"""Re-run the bounded, offline function inventory in the reference documentation.

Print observations with the installed SQLGlot; --check also compares the reviewed
baseline. This is evidence for future catalogs, not a runtime function registry.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError
from sqlglot.optimizer.annotate_types import annotate_types

from dbt_extra.analysis.lineage import qualify_columns


AUDIT = Path(__file__).resolve().parents[1] / "docs/reference/sql-functions/audit.md"
SCHEMA = {"t": {"id": "BIGINT"}}


@dataclass(frozen=True)
class Case:
    dialect: str
    expression: str
    arity: str
    kind: str
    policy: str
    volatility: str
    ast: str
    inferred: str
    classification: str
    source: str


def cases(path=AUDIT):
    """The Markdown inventory is the single source of audit inputs/baselines."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| `"):
            values = [v.strip().strip("`") for v in line.strip("| ").split(" | ")]
            yield Case(*values)


def observe(case):
    try:
        node = parse_one(case.expression, read=case.dialect)
        # STRING_SPLIT is a table source in Fabric, not a SELECT-list scalar.
        query = ("SELECT * FROM " + case.expression if case.kind == "generator" and case.dialect == "fabric"
                 else "SELECT " + case.expression + " AS result FROM t")
        tree = parse_one(query, read=case.dialect)
    except ParseError:
        return "ParseError", "unresolved", "unsupported_syntax"

    ast = type(node).__name__
    # Native/gap recognition and scalar inference are separate observations.
    # Do not mistake a generator's absent scalar type for a native inference gap.
    inferred = "not_scalar"
    if case.kind != "generator":
        qualified = qualify_columns(tree, SCHEMA, case.dialect)
        # Measure SQLGlot itself, independently of implemented local catalogs.
        typed = annotate_types(qualified.copy(), schema=SCHEMA, dialect=case.dialect)
        types = [p.type.sql(dialect=case.dialect) for p in typed.selects
                 if not p.is_star and p.type and p.type.this not in {
                     exp.DataType.Type.UNKNOWN, exp.DataType.Type.NULL}]
        inferred = next(iter(types), "unresolved")
    if isinstance(node, exp.Anonymous):
        classification = "recognition_gap"
    elif isinstance(node, exp.Dot):
        classification = "qualified_call"
    elif case.kind != "generator" and inferred == "unresolved":
        classification = "native_inference_gap"
    else:
        classification = "native"
    return ast, inferred, classification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on changes to the reviewed baseline")
    args = parser.parse_args()
    print(f"SQLGlot {sqlglot.__version__}; schema t.id BIGINT; offline only")
    failures = []
    for case in cases():
        actual = observe(case)
        print(f"{case.dialect} | {case.expression} | " + " | ".join(actual))
        if args.check and actual != (case.ast, case.inferred, case.classification):
            failures.append(f"{case.dialect}: {case.expression}: expected "
                            f"{(case.ast, case.inferred, case.classification)!r}, got {actual!r}")
    if failures:
        parser.exit(1, "\n".join(failures) + "\nReview dependency changes; do not blindly update the baseline.\n")


if __name__ == "__main__":
    main()
