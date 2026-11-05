"""Query scopes and checked projection/clause edits, independent of review formats."""

import copy
import re

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from dbt_extra.errors import SpecError
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.macros import single_expression, contains_opaque
from dbt_extra.sql.renderer import render


CLAUSES = {"from_", "joins", "where", "group", "having", "qualify", "order", "limit", "offset", "windows"}


def relation_tables(tree):
    """Yield physical relation nodes, excluding references to scoped SQL CTEs."""
    for scope in traverse_scope(tree):
        for table in scope.tables:
            if len(table.parts) == 1 and isinstance(scope.sources.get(table.alias_or_name), Scope):
                continue
            yield table


def volatile(tree):
    return any(isinstance(n, exp.Anonymous) or n.key in {"rand", "randn", "uuid", "currenttimestamp", "currentdate", "currenttime", "nextvaluefor"}
               for n in tree.walk())


def query_scopes(tree):
    """Address named CTEs by AST path, not potentially shadowed names."""
    result = []

    def visit(node, path):
        if isinstance(node, exp.CTE):
            result.append((node.alias, path + ["this"], node.this))
        for key, value in node.args.items():
            if isinstance(value, exp.Expression):
                visit(value, path + [key])
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    if isinstance(child, exp.Expression):
                        visit(child, path + [key, index])

    visit(tree, [])
    return result + [("OUTPUT", [], tree)]


def scope_at(tree, path):
    node = tree
    for key in path:
        node = node[key] if isinstance(key, int) else node.args[key]
    return node


def editable_select(node):
    return (isinstance(node, exp.Select)
            and not any(value for key, value in node.args.items() if key not in CLAUSES | {"expressions", "with_", "distinct"})
            and not (node.args.get("distinct") and node.args["distinct"].args.get("on")))


def clauses_text(node, parsed, dialect):
    query = node.copy()
    query.set("expressions", [exp.Star()])
    query.set("with_", None)
    query.set("distinct", None)
    return re.sub(r"^SELECT\s+\*\s*", "", render(query, parsed, dialect).strip().rstrip(";"), count=1)


def rewrite_scopes(parsed, edits, dialect, context, *, parser=None):
    """Apply checked clause/projection changes to original authored scopes."""
    parse = parser or (lambda code: parse_authored(code, dialect, context))
    for edit in edits:
        try:
            query = scope_at(parsed.tree, edit["path"])
        except (KeyError, IndexError, AttributeError, TypeError) as exc:
            raise SpecError(f"SQL scope was replaced by another edit; edit these scopes separately: {context}") from exc
        if not editable_select(query):
            raise SpecError(f"Structured SQL rewriting unavailable: {context}")
        values = edit["changes"]
        if "projection" in edit:
            original = query.selects[edit["projection"]]
            if original.output_name != edit["column"] or original.is_star or contains_opaque(original, parsed):
                raise SpecError(f"Ambiguous STEP expression: {context}")
            value = parse("SELECT " + values["expression"])
            candidate = single_expression(value, edit["column"])
            alias = original.args["alias"].copy() if isinstance(original, exp.Alias) else exp.to_identifier(edit["column"], quoted=True)
            original.replace(exp.Alias(this=candidate.copy(), alias=alias))
            parsed.refs.update(value.refs)
            parsed.macros.update(value.macros)
            parsed.macro_aliases.update(value.macro_aliases)
            continue
        if "clauses" in values:
            candidate = parse("SELECT 1\n" + values["clauses"])
            if (not editable_select(candidate.tree) or candidate.prefix or candidate.tree.args.get("with_")
                    or candidate.tree.args.get("distinct") or len(candidate.tree.selects) != 1
                    or candidate.tree.selects[0] != exp.Literal.number(1) or candidate.opaque_macros):
                raise SpecError(f"Expected SELECT clauses only (FROM/JOIN/WHERE/GROUP BY/etc.): {context}")
            for key in CLAUSES:
                query.set(key, copy.deepcopy(candidate.tree.args.get(key)))
            parsed.refs.update(candidate.refs)
            parsed.macros.update(candidate.macros)
        if "distinct" in values:
            value = values["distinct"].strip().lower()
            if value not in {"", "true", "false"}:
                raise SpecError("Distinct must be true, false, or blank")
            query.set("distinct", exp.Distinct() if value == "true" else None)
