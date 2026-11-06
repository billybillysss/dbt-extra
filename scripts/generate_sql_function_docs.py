"""Generate the function ownership matrix without changing runtime SQL.

Regenerates marked inventories, catalog counts and four-column data tables. Handwritten
policies, examples and source notes outside those generated data are preserved.
Run from the checkout with --write to regenerate or --check to detect drift.
"""

import argparse
from functools import cache
import json
from pathlib import Path
import re

import sqlglot
from sqlglot import Dialect, exp, parse_one
from sqlglot.errors import ParseError

from dbt_extra.analysis.type_inference import NATIVE_RETURN_TYPES, NATIVE_TYPE_RULES
from dbt_extra.sql.functions import CATALOG


DOCS = Path(__file__).resolve().parents[1] / "docs/reference/sql-functions"
SOURCES = DOCS / "function_sources.json"
START = "<!-- BEGIN GENERATED FUNCTION INVENTORY -->"
END = "<!-- END GENERATED FUNCTION INVENTORY -->"
DIALECTS = {
    "duckdb": "DuckDB",
    "postgres": "PostgreSQL",
    "snowflake": "Snowflake",
    "bigquery": "BigQuery",
    "spark": "Spark",
    "tsql": "T-SQL",
    "fabric": "Fabric",
    "databricks": "Databricks",
    "redshift": "Redshift",
    "trino": "Trino",
    "athena": "Athena",
}
SYMBOLS = {"SQLGlot": "S", "dbt-extra": "E", "SQLGlot + dbt-extra": "B", "Neither": "×"}

# Representative SQL spellings for the reviewed native return-type repairs.
# Keep ownership separate from the local Anonymous-function registrations.
NATIVE_EXAMPLES = {
    "snowflake": {"IS_ARRAY": "is_array(parse_json('[]'))", "TO_NUMBER": "to_number('1.2',10,2)"},
    "redshift": {
        "SOUNDEX": "soundex('hello')",
        "JSON_EXTRACT_PATH_TEXT": "json_extract_path_text('{}', 'a')",
        "JSON_PARSE": "json_parse('{}')",
    },
    "trino": {"CURRENT_TIMEZONE": "current_timezone()", "APPROX_PERCENTILE": "approx_percentile(id,0.5)"},
}
for _dialect in ("postgres", "duckdb", "spark", "databricks", "trino", "athena"):
    _array = "array(1,2)" if _dialect in {"spark", "databricks"} else "ARRAY[1,2]"
    NATIVE_EXAMPLES.setdefault(_dialect, {})["ARRAY_POSITION"] = f"array_position({_array},2)"
NATIVE_EXAMPLES["databricks"]["PARSE_JSON"] = "parse_json('{}')"
NATIVE_EXAMPLES["duckdb"].update({
    "STRPOS": "strpos('abc','b')", "SIGN": "sign(id)", "TO_TIMESTAMP": "to_timestamp(1.0)",
    "GET_CURRENT_TIME": "get_current_time()", "WEEKOFYEAR": "weekofyear(DATE '2026-01-01')",
    "APPROX_QUANTILE": "approx_quantile(id,0.5)", "REPEAT": "repeat('a',2)",
    "JSON_EXTRACT_STRING": "json_extract_string('{}','$.a')", "ROUND": "round(id,0)",
})
for _dialect in ("postgres", "duckdb", "spark", "databricks", "tsql", "fabric", "redshift"):
    NATIVE_EXAMPLES.setdefault(_dialect, {}).update({"SUM": "sum(id)", "AVG": "avg(id)"})
NATIVE_EXAMPLES["postgres"].update({
    name: f"{name.lower()}(id)" for name in ("STDDEV", "STDDEV_POP", "STDDEV_SAMP", "VARIANCE", "VAR_POP")
})


@cache
def sqlglot_names(dialect):
    """Enumerate named function registries, not arbitrary parseable SQL calls."""
    parser = Dialect.get_or_raise(dialect).parser_class
    return (
        set(parser.FUNCTIONS)
        | set(parser.FUNCTION_PARSERS)
        | {token.name for token in parser.NO_PAREN_FUNCTIONS}
    )


@cache
def native_repairs(dialect):
    examples = NATIVE_EXAMPLES.get(dialect, {})
    repairs = {}
    covered = set()
    for name, expression in examples.items():
        node_type = type(parse_one(expression, read=dialect))
        repairs[name] = NATIVE_RETURN_TYPES.get(dialect, {}).get(node_type, "argument-dependent; reviewed overloads only")
        covered.add(node_type)
        for alias in set(node_type.sql_names()) & sqlglot_names(dialect):
            alias_expression = alias + "(" + expression.split("(", 1)[1]
            if type(parse_one(alias_expression, read=dialect)) is node_type:
                repairs[alias] = repairs[name]
    if covered != set(NATIVE_RETURN_TYPES.get(dialect, {})) | set(NATIVE_TYPE_RULES.get(dialect, {})):
        raise ValueError(f"Review native return-type documentation for {dialect}")
    return repairs


@cache
def source_catalog():
    return json.loads(SOURCES.read_text(encoding="utf-8"))


@cache
def implementation(dialect, name):
    if name.lower() in CATALOG[dialect]:
        return "dbt-extra"
    if name in native_repairs(dialect):
        return "SQLGlot + dbt-extra"
    if name in sqlglot_names(dialect):
        return "SQLGlot"
    if dialect == "bigquery" and "." in name:
        prefix, member = name.split(".", 1)
        # BigQuery explicitly re-enters its named parsers for these namespaces.
        if prefix in {"AI", "ML", "NET", "SAFE"} and member in sqlglot_names(dialect):
            return "SQLGlot"
    # Typed casts and some keyword functions live outside the named registries.
    # Merely accepting an Anonymous/qualified call is not native recognition.
    expressions = [name] + [f"{name}({', '.join(['NULL'] * arity)})" for arity in range(5)]
    for expression in expressions:
        try:
            node = parse_one(expression, read=dialect)
        except (ParseError, ValueError, TypeError, AttributeError, IndexError):
            # Synthetic NULL arguments can violate a parser's required shape;
            # failed probes are not evidence of named recognition.
            continue
        if isinstance(node, exp.Dot):
            node = node.expression
        if isinstance(node, exp.Func) and not isinstance(node, exp.Anonymous):
            return "SQLGlot"
    return "Neither"


@cache
def all_names(dialect):
    return (sqlglot_names(dialect)
            | {name.upper() for name in CATALOG[dialect]}
            | set(source_catalog()["dialects"][dialect]["names"]))


def inventory(dialect):
    native = sqlglot_names(dialect)
    local = {name.upper(): spec for name, spec in CATALOG[dialect].items()}
    repairs = native_repairs(dialect)
    if set(local) & native:
        raise ValueError(f"Review overlapping SQLGlot/local registrations for {dialect}")
    if not set(repairs) <= native:
        raise ValueError(f"Review native function spellings for {dialect}")
    return [(name, implementation(dialect, name)) for name in sorted(all_names(dialect))]


def matrix():
    """One row per spelling; absent entries stay distinct from known gaps."""
    if set(DIALECTS) != set(CATALOG):
        raise ValueError("Review matrix columns for changed dialect catalogs")
    owners = {dialect: dict(inventory(dialect)) for dialect in DIALECTS}
    names = set.union(*(set(entries) for entries in owners.values()))
    return [
        (name, tuple(SYMBOLS[owners[dialect][name]] if name in owners[dialect] else "—"
                     for dialect in DIALECTS))
        for name in sorted(names)
    ]


def render(page):
    snapshot = source_catalog()
    lines = [START]
    if page == "README":
        rows = matrix()
        lines.extend([
            "## Function implementation matrix",
            "",
            f"**{len(rows)} function names · {len(DIALECTS)} dialects**. "
            f"Generated against **SQLGlot {sqlglot.__version__}** and the current dbt-extra catalogs.",
            f"Official documentation snapshot: **{snapshot['snapshot_date']}**.",
            "",
            "**S** = SQLGlot · **E** = dbt-extra · **B** = both · **×** = neither · "
            "**—** = not listed for that dialect.",
            "",
            "These are analysis/recognition entries, not warehouse compatibility guarantees.",
            "Inherited SQLGlot names may not execute in a dialect; **—** does not prove",
            "warehouse incompatibility. See [scope and symbol definitions](#reading-the-matrix).",
            "Dialect headers link to the detailed local type policies.",
            "",
            "| SQL function | " + " | ".join(
                f"[{label}]({dialect}.md)" for dialect, label in DIALECTS.items()) + " |",
            "| --- | " + " | ".join(":---:" for _ in DIALECTS) + " |",
        ])
        lines.extend(f"| `{name}` | " + " | ".join(cells) + " |" for name, cells in rows)
    else:
        lines.extend([
            "## Function implementation reference",
            "",
            "All function names and implementation symbols are in the single",
            "[function implementation matrix](README.md#function-implementation-matrix).",
        ])
        source = snapshot["dialects"][page]
        lines.extend([
            "",
            f"Source scope: {source['version']}.",
            f"See the [official-source snapshot](function_sources.json) for all source URLs "
            f"(collected {snapshot['snapshot_date']}).",
        ])
        if page == "athena":
            lines.extend([
                "AWS-linked Trino references are candidates, not proof of Athena engine-3",
                "availability; Athena does not inherit Trino's local implementations.",
            ])
    lines.append(END)
    return "\n".join(lines) + "\n"


def document(dialect, text):
    if dialect == "README":
        for key, entries in CATALOG.items():
            text = re.sub(rf"(\| `{key}` \| )\d+( \|)", rf"\g<1>{len(entries)}\2", text)
        text = re.sub(r"These \*\*\d+ dialect-local entries\*\*",
                      f"These **{sum(map(len, CATALOG.values()))} dialect-local entries**", text)
    else:
        # The table is a projection of the runtime catalog, not a second source
        # of function facts. Restrict replacement to the existing data-only
        # schema; never swallow surrounding handwritten notes or extra columns.
        pattern = r"(\| Function \| Kind \| Return (?:type )?policy \| Volatility \|\n\| --- \| --- \| --- \| --- \|\n)((?:\| `[^\n]*\n)*)"
        def table(match):
            if any(len(row.split(" | ")) != 4 for row in match[2].splitlines()):
                raise ValueError(f"Review nonstandard local policy table in {dialect}")
            rows = [f"| `{spec.name}` | {spec.kind} | "
                    + (f"`{spec.returns}`" if spec.returns else "unresolved / input-dependent")
                    + f" | {spec.volatility} |\n" for spec in CATALOG[dialect].values()]
            return match[1] + "".join(rows)
        text = re.sub(pattern, table, text)
    block = render(dialect)
    if START not in text and END not in text:
        return text.rstrip("\n") + "\n\n" + block
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError(f"Malformed inventory markers in {dialect}.md")
    before, remaining = text.split(START)
    _, after = remaining.split(END)
    return before + block.rstrip("\n") + after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate marked inventory blocks")
    mode.add_argument("--check", action="store_true", help="fail if inventories need regeneration")
    args = parser.parse_args()
    changed = []
    for page in ["README", *DIALECTS]:
        path = DOCS / f"{page}.md"
        text = path.read_text(encoding="utf-8")
        expected = document(page, text)
        if text != expected:
            changed.append(path.name)
            if args.write:
                path.write_text(expected, encoding="utf-8", newline="\n")
    if args.check and changed:
        parser.exit(1, "Function inventories need regeneration: " + ", ".join(changed) + "\n")
    print(f"SQLGlot {sqlglot.__version__}: {len(DIALECTS)}-dialect function matrix "
          + (f"generated ({len(changed)} changed)." if args.write else "up to date."))


if __name__ == "__main__":
    main()
