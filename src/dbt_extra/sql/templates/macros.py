"""Local macro definitions and independent call classification."""

from dataclasses import dataclass

from jinja2 import nodes
from sqlglot import exp

from dbt_extra.errors import SpecError
from dbt_extra.sql.models import UnsupportedSQL
from dbt_extra.sql.parser import read_query
from dbt_extra.sql.templates.interpreter import StaticMacros
from dbt_extra.sql.templates.syntax import call_name, output_spans, validate_template


def macro_definitions(sources):
    """Collect top-level definitions from (package, code, context) records."""
    definitions = {}
    for package, code, context in sources:
        for macro in validate_template(code, context).body:
            if not isinstance(macro, nodes.Macro):
                continue  # Conditional definitions require runtime context.
            key = package + "." + macro.name
            if key in definitions:
                raise UnsupportedSQL(f"Ambiguous authored macro: {key}")
            definitions[key] = macro
    return definitions


def macro_calls(code):
    return [(start, end, raw, node) for start, end, raw, node in output_spans(code)
            if isinstance(node, nodes.Call) and call_name(node.node) not in {"ref", "source", "config"}]


@dataclass
class MacroCall:
    start: int
    end: int
    raw: str
    name: str
    sql: str | None = None
    single_column: bool = False
    reason: str = ""
    alias: exp.Expression | None = None


def classify_calls(code, dialect, context="SQL", *, definitions=None, package="static"):
    """Resolve calls independently without inferring opaque output shapes."""
    interpreter = StaticMacros(definitions, package=package)
    results = []
    for start, end, raw, node in macro_calls(code):
        call = MacroCall(start, end, raw, call_name(node.node))
        results.append(call)
        try:
            # One expensive call must not affect another call's budget.
            interpreter.budget = 10000
            if raw.startswith("{{-") or raw.endswith("-}}"):
                raise UnsupportedSQL("Whitespace-controlled macro calls retain their original template boundary")
            result = interpreter.call(node)
            if any(marker in result for marker in ("{{", "{%", "{#")):
                raise UnsupportedSQL("Macro output containing unevaluated Jinja remains opaque")
            call.sql = result
            try:
                query = read_query("SELECT " + result, context, dialect)
                call.single_column = (isinstance(query, exp.Select) and len(query.selects) == 1
                    and not any(v for k, v in query.args.items() if k != "expressions")
                    and not query.selects[0].is_star)
                if call.single_column and isinstance(query.selects[0], exp.Alias):
                    call.alias = query.selects[0].args["alias"]
            except SpecError:
                pass  # A resolved SQL fragment need not be a projection.
            if not call.single_column:
                call.reason = f"Macro {call.name} may emit multiple columns or SQL clauses; source rewriting requires scalar macros"
        except SpecError as exc:
            call.reason = str(exc)
    return results


def contains_opaque(node, parsed):
    """Opaque placeholders are boundaries, never evidence of scalar output."""
    return any(n.name.lower() in parsed.opaque_macros for n in node.find_all(exp.Anonymous))


def single_expression(parsed, column):
    """Validate an expression edit, including an alias emitted by a known macro."""
    query = parsed.tree
    if (not isinstance(query, exp.Select) or len(query.selects) != 1
            or any(v for k, v in query.args.items() if k != "expressions")
            or query.selects[0].is_star or parsed.opaque_macros):
        raise SpecError(f"Expected one resolved unaliased expression: {column}")
    expression = query.selects[0]
    if isinstance(expression, exp.Alias):
        token = expression.this.name.lower() if isinstance(expression.this, exp.Anonymous) else None
        if parsed.macro_aliases.get(token) != column or expression.alias != column:
            raise SpecError(f"Expected one unaliased expression: {column}")
        expression = expression.this
    return expression
