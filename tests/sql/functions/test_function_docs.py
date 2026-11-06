"""Function ownership documentation covers the current upstream/local registries."""

from pathlib import Path
import json
import re
import runpy

import pytest
from sqlglot import Dialect

from dbt_extra.sql.functions import CATALOG


GENERATOR = runpy.run_path(str(
    Path(__file__).resolve().parents[3] / "scripts/generate_sql_function_docs.py"
))
COLLECTOR = runpy.run_path(str(
    Path(__file__).resolve().parents[3] / "scripts/collect_sql_function_sources.py"
))


@pytest.mark.parametrize("dialect", sorted(CATALOG))
def test_inventory_covers_all_registered_names_once_with_correct_ownership(dialect):
    rows = GENERATOR["inventory"](dialect)
    names = [name for name, _ in rows]
    parser = Dialect.get_or_raise(dialect).parser_class
    native = (set(parser.FUNCTIONS) | set(parser.FUNCTION_PARSERS)
              | {token.name for token in parser.NO_PAREN_FUNCTIONS})
    local = {name.upper() for name in CATALOG[dialect]}
    assert names == sorted(set(names))
    official = set(GENERATOR["source_catalog"]()["dialects"][dialect]["names"])
    assert set(names) == native | local | official
    owners = dict(rows)
    assert set(owners.values()) <= {"SQLGlot", "dbt-extra", "SQLGlot + dbt-extra", "Neither"}
    assert all(owners[name] == "dbt-extra" for name in local)
    repairs = GENERATOR["native_repairs"](dialect)
    assert all(owners[name] == "SQLGlot" for name in native - set(repairs))
    for name in repairs:
        assert owners[name] == "SQLGlot + dbt-extra"


def test_matrix_covers_each_function_once_and_keeps_missing_distinct_from_neither():
    rows = GENERATOR["matrix"]()
    names = [name for name, _ in rows]
    assert names == sorted(set(names))
    assert set(names) == set.union(*(GENERATOR["all_names"](dialect) for dialect in CATALOG))
    for name, cells in rows:
        assert len(cells) == len(CATALOG)
        for dialect, symbol in zip(GENERATOR["DIALECTS"], cells):
            if name not in GENERATOR["all_names"](dialect):
                assert symbol == "—"
            else:
                owner = GENERATOR["implementation"](dialect, name)
                assert symbol == GENERATOR["SYMBOLS"][owner]
    assert set(symbol for _, cells in rows for symbol in cells) == {"S", "E", "B", "×", "—"}
    matrix = dict(rows)
    assert matrix["ABS"] == ("S",) * len(CATALOG)
    columns = list(GENERATOR["DIALECTS"])
    assert matrix["GETENV"][columns.index("duckdb")] == "×"
    assert matrix["INVOKER_PRINCIPAL"][columns.index("athena")] == "E"
    assert matrix["INVOKER_PRINCIPAL"][columns.index("trino")] == "—"
    assert matrix["IS_ARRAY"][columns.index("snowflake")] == "B"


@pytest.mark.parametrize("dialect,name,owner", [
    ("duckdb", "GETENV", "Neither"),
    ("bigquery", "HLL_COUNT.INIT", "Neither"),
    ("bigquery", "ML.FEATURES_AT_TIME", "SQLGlot"),
    ("bigquery", "AI.GENERATE_BOOL", "SQLGlot"),
    ("databricks", "TRY_ADD", "SQLGlot"),
    ("fabric", "JSON_VALUE", "SQLGlot"),
    ("trino", "CURRENT_TIMEZONE", "SQLGlot + dbt-extra"),
    ("redshift", "JSON_EXTRACT_SCALAR", "SQLGlot + dbt-extra"),
    ("athena", "INVOKER_PRINCIPAL", "dbt-extra"),
    ("trino", "INVOKER_PRINCIPAL", "Neither"),
    ("databricks", "BROUND", "dbt-extra"),
    ("spark", "BROUND", "dbt-extra"),
])
def test_ownership_includes_unsupported_names_without_inheriting_related_catalogs(dialect, name, owner):
    assert GENERATOR["implementation"](dialect, name) == owner


def test_matrix_documentation_is_current_and_has_all_dialect_headers():
    text = (GENERATOR["DOCS"] / "README.md").read_text(encoding="utf-8")
    # Fresh-dependency package tests may use a newer SQLGlot than the snapshot.
    # Ignore only its generation-version label, not changes to the inventory.
    version = re.search(r"Generated against \*\*SQLGlot ([^*]+)\*\*", text)
    assert version is not None
    expected = text.replace(
        version[0],
        f"Generated against **SQLGlot {GENERATOR['sqlglot'].__version__}**",
        1,
    )
    assert GENERATOR["document"]("README", text) == expected
    block = text.split(GENERATOR["START"])[1]
    assert "| SQL function |" in block
    assert all(f"[{label}]({dialect}.md)" in block
               for dialect, label in GENERATOR["DIALECTS"].items())


def test_index_collection_ignores_navigation_and_wildcard_groups(monkeypatch):
    html = '''<nav><a href="/functions/not_a_function">Navigation</a></nav>
    <table><tr><td><a href="/functions/abs"><code>ABS</code></a></td></tr>
    <tr><td><a href="/functions/year">YEAR*</a></td></tr></table>'''
    monkeypatch.setitem(COLLECTOR["linked_index"].__globals__, "fetch", lambda _: html)
    result = COLLECTOR["linked_index"]("https://example.com", "/functions/", "test", tables_only=True)
    assert result["names"] == ["ABS"]


def test_databricks_collection_keeps_aggregate_and_generator_names(monkeypatch):
    html = '''<a href=/functions/sum>sum aggregate function</a>
    <a href=/functions/explode>explode table-valued generator function</a>
    <a href=/functions/date_add>date_add (days) function</a>
    <a href=/functions/next>next function for MATCH_RECOGNIZE</a>
    <a href=/functions/and>and predicate</a>'''
    monkeypatch.setitem(COLLECTOR["linked_index"].__globals__, "fetch", lambda _: html)
    result = COLLECTOR["linked_index"]("https://example.com", "/functions/", "test", "function")
    assert result["names"] == ["DATE_ADD", "EXPLODE", "NEXT", "SUM"]


def test_fabric_collection_requires_warehouse_not_sql_database_evidence(monkeypatch):
    responses = {
        "https://api.github.com/repos/MicrosoftDocs/sql-docs/contents/docs/t-sql/functions": json.dumps([
            {"name": "warehouse.md", "download_url": "warehouse"},
            {"name": "database.md", "download_url": "database"},
        ]),
        "warehouse": "# CAST and CONVERT (Transact-SQL)\n"
                     "[!INCLUDE [](../../includes/applies-to-version/sql-fabricdw.md)]",
        "database": "# DATABASE_ONLY (Transact-SQL)\n"
                    "[!INCLUDE [](../../includes/applies-to-version/sql-fabricsqldb.md)]",
    }
    monkeypatch.setitem(COLLECTOR["microsoft"].__globals__, "fetch", responses.__getitem__)
    tsql, fabric = COLLECTOR["microsoft"]()
    assert tsql["names"] == ["CAST", "CONVERT", "DATABASE_ONLY"]
    assert fabric["names"] == ["CAST", "CONVERT"]


def test_official_snapshot_has_expected_names_and_no_navigation_labels():
    sources = GENERATOR["source_catalog"]()["dialects"]
    assert set(sources) == set(CATALOG)
    assert "AUTOENCODER" not in sources["bigquery"]["names"]
    assert "HLL_COUNT.INIT" in sources["bigquery"]["names"]
    assert "ALL" not in sources["trino"]["names"]
    assert {"AVG", "EXPLODE", "READ_KAFKA"} <= set(sources["databricks"]["names"])
    assert "GETENV" in sources["duckdb"]["names"]


@pytest.mark.parametrize("dialect", sorted(CATALOG))
def test_checked_in_inventory_is_current_and_keeps_local_policies(dialect):
    text = (GENERATOR["DOCS"] / f"{dialect}.md").read_text(encoding="utf-8")
    assert GENERATOR["document"](dialect, text) == text
    before = text.split(GENERATOR["START"])[0]
    assert "| Function | Kind | Return" in before
    assert all(f"| `{name}` |" in before for name in CATALOG[dialect])
    after = text.split(GENERATOR["START"])[1]
    assert "README.md#function-implementation-matrix" in after
    assert "| Function |" not in after


def test_regeneration_only_replaces_marked_block():
    start, end = GENERATOR["START"], GENERATOR["END"]
    text = f"User policies\n\n{start}\noutdated\n{end}\n\nUser notes\n"
    updated = GENERATOR["document"]("README", text)
    assert updated.startswith("User policies\n\n" + start)
    assert updated.endswith(end + "\n\nUser notes\n")
    assert "outdated" not in updated
    assert GENERATOR["document"]("README", updated) == updated


def test_missing_inventory_is_appended_without_replacing_existing_text():
    updated = GENERATOR["document"]("README", "User policies\n")
    assert updated.startswith("User policies\n\n" + GENERATOR["START"])


def test_catalog_table_is_regenerated_without_replacing_handwritten_policies():
    text = ("Authored policy\n\n| Function | Kind | Return policy | Volatility |\n"
            "| --- | --- | --- | --- |\n| `outdated` | scalar | `INT` | immutable |\n\nAuthored notes\n")
    updated = GENERATOR["document"]("duckdb", text)
    assert updated.startswith("Authored policy\n\n| Function |")
    assert "\n\nAuthored notes\n" in updated
    assert "outdated" not in updated
    assert all(f"| `{name}` |" in updated for name in CATALOG["duckdb"])
    assert GENERATOR["document"]("duckdb", updated) == updated


@pytest.mark.parametrize("markers", [
    GENERATOR["START"], GENERATOR["END"],
    GENERATOR["START"] * 2 + GENERATOR["END"],
])
def test_malformed_markers_are_not_overwritten(markers):
    with pytest.raises(ValueError, match="Malformed inventory markers"):
        GENERATOR["document"]("duckdb", markers)


def test_check_mode_fails_for_stale_documentation(tmp_path, monkeypatch, capsys):
    namespace = GENERATOR["main"].__globals__
    monkeypatch.setitem(namespace, "DOCS", tmp_path)
    for dialect in ["README", *CATALOG]:
        (tmp_path / f"{dialect}.md").write_text("Existing policies\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["generate_sql_function_docs.py", "--check"])
    with pytest.raises(SystemExit) as exc:
        GENERATOR["main"]()
    assert exc.value.code == 1
    assert "need regeneration" in capsys.readouterr().err
    assert (tmp_path / "duckdb.md").read_text(encoding="utf-8") == "Existing policies\n"
