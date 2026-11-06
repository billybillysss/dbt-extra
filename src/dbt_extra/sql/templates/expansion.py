"""Top-level static interpretation, using the same allowlist and work budgets as macros."""

import hashlib

from jinja2 import nodes

from dbt_extra.sql.models import UnsupportedSQL
from dbt_extra.sql.templates.interpreter import StaticMacros
from dbt_extra.sql.templates.syntax import call_name, output_spans, validate_template


def expand_static(code, context="SQL", *, definitions=None, package="static"):
    class TopLevel(StaticMacros):
        depth = 0

        def body(self, body, values, active):
            self.depth += 1
            try:
                if self.depth > 20:
                    raise UnsupportedSQL("Static template nesting limit exceeded")
                return super().body(body, values, active)
            finally:
                self.depth -= 1

    replacements, preserved = [], {}
    for start, end, raw, node in output_spans(code):
        name = call_name(node.node) if isinstance(node, nodes.Call) else node.name if isinstance(node, nodes.Name) else None
        if name not in {"ref", "source", "config", "this"}:
            continue
        if isinstance(node, nodes.Call) and name != "config" and (
            node.dyn_args or node.dyn_kwargs or any(not isinstance(a, nodes.Const) for a in node.args)
            or any(not isinstance(k.value, nodes.Const) for k in node.kwargs)
        ):
            raise UnsupportedSQL(f"Dynamic {name} remains opaque in static templates")
        token = "extra_static_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        if token.casefold() in code.casefold():
            raise UnsupportedSQL("Reserved static template token collision")
        # Keep whitespace-control semantics in the interpreted template; the
        # reduced dbt call no longer needs to trim already-consumed whitespace.
        preserved[token] = "{{" + raw[3 if raw.startswith("{{-") else 2:-3 if raw.endswith("-}}") else -2] + "}}"
        replacement = ("{{-" if raw.startswith("{{-") else "{{") + repr(token) + ("-}}" if raw.endswith("-}}") else "}}")
        replacements.append((start, end, replacement))
    for start, end, replacement in reversed(replacements):
        code = code[:start] + replacement + code[end:]
    template = validate_template(code, context)
    interpreter = TopLevel(definitions, package=package)
    try:
        result = interpreter.body(template.body, {}, ())
    except UnsupportedSQL as exc:
        raise UnsupportedSQL(f"{context}: static Jinja blocked: {exc}") from exc
    if any(marker in result for marker in ("{{", "{%", "{#")):
        raise UnsupportedSQL("Static template output containing unevaluated Jinja remains opaque")
    for token, raw in preserved.items():
        result = result.replace(token, raw)
    return result
