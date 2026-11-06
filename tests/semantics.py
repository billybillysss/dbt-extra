"""Execution oracles independent of optimizer parsing and template interpretation."""

from collections import Counter

from jinja2 import Environment, StrictUndefined
import pytest
from sqlglot import parse_one


def ordered_query(sql, dialect="duckdb"):
    """Only a final ORDER BY promises order; an inner ORDER BY can select LIMIT rows."""
    return bool(parse_one(sql, read=dialect).args.get("order"))


def result(connection, sql, *, ordered=None):
    """Require successful execution and compare the complete output interface."""
    cursor = connection.execute(sql)
    names = [column[0] for column in cursor.description]
    types = [str(column[1]) for column in cursor.description]
    rows = cursor.fetchall()
    if ordered is None:
        ordered = ordered_query(sql)
    return names, types, rows if ordered else Counter(rows)


def error_signature(exc):
    # Retain the actual reason, not just a broad exception class. SQL position /
    # caret excerpts differ legitimately after formatting or alias generation.
    detail = str(exc).split("\nLINE ", 1)[0].split("\n\n", 1)[0].strip()
    return type(exc).__name__, getattr(exc, "sqlstate", None), detail


def assert_equivalent(connection, original, candidate, *, ordered=None, expected_error=None):
    """Success is the default contract; expected errors need a class and reason."""
    if expected_error is not None:
        kind, reason = expected_error
        with pytest.raises(kind, match=reason) as before:
            connection.execute(original).fetchall()
        with pytest.raises(kind, match=reason) as after:
            connection.execute(candidate).fetchall()
        assert error_signature(before.value) == error_signature(after.value)
        return
    if ordered is None:
        ordered = ordered_query(original)
    assert result(connection, original, ordered=ordered) == result(connection, candidate, ordered=ordered), candidate


def render_jinja(root, code):
    """Real Jinja oracle for controlled fixtures, never the production interpreter.

    Relations are local test tables. This is not a replacement for dbt's context;
    a separate dbt integration test covers the actual adapter/compiler boundary.
    """
    environment = Environment(undefined=StrictUndefined, keep_trailing_newline=True)
    environment.globals.update(
        ref=lambda *args, **kwargs: args[-1],
        source=lambda *args: ".".join(args),
        config=lambda **kwargs: "",
    )
    definitions = "\n".join(path.read_text(encoding="utf-8") for path in sorted((root / "macros").rglob("*.sql")))
    module = environment.from_string(definitions).make_module()
    environment.globals.update({name: value for name, value in vars(module).items() if not name.startswith("_")})
    # Native fixture projects use this package name for explicit local calls.
    environment.globals["shop"] = module
    return environment.from_string(code).render()
