"""Bounded, allowlisted interpretation of local SQL-generating macros.

No Python/Jinja execution, adapter access, dbt invocation or warehouse calls.
Unknown constructs stay opaque rather than guessing their output shape.
"""

import hashlib
from dataclasses import dataclass

from jinja2 import nodes
from sqlglot import exp

from dbt_extra.errors import SpecError
from dbt_extra.sql.jinja import validate_template
from dbt_extra.sql.parser import UnsupportedSQL, parse_authored, read_query
from dbt_extra.sql.shorthand import call_name, output_spans


LIMIT = 100000


class StaticMacros:
    def __init__(self, project):
        self.project = project
        self.definitions = {}
        self.budget = 10000
        for resource in project.resources.values():
            if resource.kind != "macro" or resource.path is None:
                continue
            template = validate_template(resource.code, resource.source_file)
            for macro in template.body:
                if not isinstance(macro, nodes.Macro):
                    continue  # Nested/conditionally defined macros need runtime context.
                key = resource.package + "." + macro.name
                if key in self.definitions:
                    raise UnsupportedSQL(f"Ambiguous authored macro: {key}")
                self.definitions[key] = macro

    def tick(self):
        self.budget -= 1
        if self.budget < 0:
            raise UnsupportedSQL("Static macro expansion budget exceeded")

    def value(self, node, values, active):
        self.tick()
        if isinstance(node, nodes.Const):
            return node.value
        if isinstance(node, nodes.Name) and node.name in values:
            return values[node.name]
        if isinstance(node, nodes.Filter) and node.name in {"upper", "lower", "trim"}:
            if node.args or node.kwargs or node.dyn_args or node.dyn_kwargs:
                raise UnsupportedSQL("String filters require no arguments")
            value = self.value(node.node, values, active)
            if not isinstance(value, str):
                raise UnsupportedSQL("String filters require a static string")
            operation = {"upper": str.upper, "lower": str.lower, "trim": str.strip}[node.name]
            return self.checked(operation(value))
        if (isinstance(node, nodes.Getattr) and isinstance(node.node, nodes.Name)
                and node.node.name == "loop" and node.attr in {"last", "first", "index", "index0", "length"}
                and isinstance(values.get("loop"), dict)):
            return values["loop"][node.attr]
        if isinstance(node, nodes.Not):
            value = self.value(node.node, values, active)
            if type(value) is bool:
                return not value
        if isinstance(node, nodes.Getattr) and node.attr in {"upper", "lower", "trim"}:
            raise UnsupportedSQL("String methods must be called without arguments")
        if isinstance(node, (nodes.And, nodes.Or)):
            left = self.value(node.left, values, active)
            if type(left) is not bool:
                raise UnsupportedSQL("Boolean operators require static booleans")
            if isinstance(node, nodes.And) and not left or isinstance(node, nodes.Or) and left:
                return left
            right = self.value(node.right, values, active)
            if type(right) is bool:
                return right
        if isinstance(node, nodes.Compare):
            left = self.value(node.expr, values, active)
            for operand in node.ops:
                right = self.value(operand.expr, values, active)
                if type(left) is not type(right) or type(left) not in {str, int, float, bool}:
                    raise UnsupportedSQL("Comparisons require same-type static scalars")
                operations = {"eq": lambda: left == right, "ne": lambda: left != right,
                              "lt": lambda: left < right, "lteq": lambda: left <= right,
                              "gt": lambda: left > right, "gteq": lambda: left >= right}
                if operand.op not in operations:
                    raise UnsupportedSQL("Unsupported static comparison")
                if not operations[operand.op]():
                    return False
                left = right
            return True
        if isinstance(node, (nodes.List, nodes.Tuple)):
            items = [self.value(v, values, active) for v in node.items]
            return tuple(items) if isinstance(node, nodes.Tuple) else items
        if isinstance(node, nodes.Concat):
            return self.checked("".join(str(self.value(v, values, active)) for v in node.nodes))
        if isinstance(node, nodes.Add):
            left, right = self.value(node.left, values, active), self.value(node.right, values, active)
            if isinstance(left, str) and isinstance(right, str) or type(left) in {int, float} and type(right) in {int, float}:
                return self.checked(left + right)
        if isinstance(node, nodes.Call):
            return self.call(node, values, active)
        raise UnsupportedSQL(f"Static macro expansion unavailable for {type(node).__name__}")

    def checked(self, value):
        if len(str(value)) > LIMIT:
            raise UnsupportedSQL("Static macro expansion size limit exceeded")
        return value

    def call(self, call, values=None, active=()):
        self.tick()
        if isinstance(call.node, nodes.Getattr) and call.node.attr in {"upper", "lower", "trim"}:
            if call.args or call.kwargs or call.dyn_args or call.dyn_kwargs:
                raise UnsupportedSQL("String methods require no arguments")
            value = self.value(call.node.node, values or {}, active)
            if not isinstance(value, str):
                raise UnsupportedSQL("String methods require a static string")
            operation = {"upper": str.upper, "lower": str.lower, "trim": str.strip}[call.node.attr]
            return self.checked(operation(value))
        name = call_name(call.node)
        if not name or call.dyn_args or call.dyn_kwargs:
            raise UnsupportedSQL("Dynamic macro invocation remains opaque")
        if name in {"ref", "source", "config", "var", "env_var", "return"}:
            raise UnsupportedSQL(f"dbt context call {name} remains opaque inside macros")
        package = active[-1].rsplit(".", 1)[0] if active else self.project.name
        key = name if "." in name else package + "." + name
        if key not in self.definitions:
            raise UnsupportedSQL(f"Macro {name} has no local static definition")
        if key in active or len(active) >= 20:
            raise UnsupportedSQL(f"Recursive macro expansion: {key}")
        macro = self.definitions[key]
        names = [a.name for a in macro.args]
        if len(call.args) > len(names):
            raise UnsupportedSQL(f"Too many arguments for macro {name}")
        bound = {n: self.value(arg, values or {}, active) for n, arg in zip(names, call.args)}
        for kw in call.kwargs:
            if kw.key not in names or kw.key in bound:
                raise UnsupportedSQL(f"Invalid argument {kw.key} for macro {name}")
            bound[kw.key] = self.value(kw.value, values or {}, active)
        defaults = dict(zip(names[len(names) - len(macro.defaults):], macro.defaults))
        for arg in names:
            if arg not in bound:
                if arg not in defaults:
                    raise UnsupportedSQL(f"Missing argument {arg} for macro {name}")
                bound[arg] = self.value(defaults[arg], bound, active)
        return self.body(macro.body, bound, (*active, key))

    def body(self, body, values, active):
        output = []
        for node in body:
            self.tick()
            if isinstance(node, nodes.Output):
                for child in node.nodes:
                    value = child.data if isinstance(child, nodes.TemplateData) else self.value(child, values, active)
                    output.append(str(value))
            elif isinstance(node, nodes.Assign) and isinstance(node.target, nodes.Name):
                values[node.target.name] = self.value(node.node, values, active)
            elif isinstance(node, nodes.For) and not node.recursive and node.test is None:
                targets = node.target.items if isinstance(node.target, nodes.Tuple) else [node.target]
                if not targets or not all(isinstance(target, nodes.Name) for target in targets):
                    raise UnsupportedSQL("Macro loops require a name or flat tuple target")
                items = self.value(node.iter, values, active)
                if not isinstance(items, (list, tuple)) or len(items) > 1000:
                    raise UnsupportedSQL("Macro loops require a bounded literal list")
                for index, item in enumerate(items):
                    unpacked = item if isinstance(node.target, nodes.Tuple) else [item]
                    if not isinstance(unpacked, (list, tuple)) or len(unpacked) != len(targets):
                        raise UnsupportedSQL("Macro loop tuple arity mismatch")
                    bound = {target.name: value for target, value in zip(targets, unpacked)}
                    loop = {"index0": index, "index": index + 1, "length": len(items),
                            "first": index == 0, "last": index == len(items) - 1}
                    output.append(self.body(node.body, {**values, **bound, "loop": loop}, active))
                if not items:
                    output.append(self.body(node.else_, dict(values), active))
            elif isinstance(node, nodes.If):
                # Only literal/argument booleans are supported; dbt execute/adapter
                # branches are intentionally never inferred.
                condition = self.value(node.test, values, active)
                if type(condition) is not bool or node.elif_:
                    raise UnsupportedSQL("Macro conditions require static booleans")
                output.append(self.body(node.body if condition else node.else_, values, active))
            else:
                raise UnsupportedSQL(f"Static macro expansion unavailable for {type(node).__name__}")
            self.checked("".join(output))
        return "".join(output)


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


def classify_calls(project, code, context="SQL"):
    """Resolve each call independently, without inferring opaque output shapes."""
    calls = macro_calls(code)
    if not calls:
        return []
    interpreter = StaticMacros(project)
    results = []
    for start, end, raw, node in calls:
        call = MacroCall(start, end, raw, call_name(node.node))
        results.append(call)
        try:
            # One unsupported/expensive call must not affect another call's budget.
            interpreter.budget = 10000
            if raw.startswith("{{-") or raw.endswith("-}}"):
                raise UnsupportedSQL("Whitespace-controlled macro calls retain their original template boundary")
            result = interpreter.call(node)
            if any(marker in result for marker in ("{{", "{%", "{#")):
                raise UnsupportedSQL("Macro output containing unevaluated Jinja remains opaque")
            call.sql = result
            try:
                query = read_query("SELECT " + result, context, project.require_dialect())
                call.single_column = (isinstance(query, exp.Select) and len(query.selects) == 1
                    and not any(v for k, v in query.args.items() if k != "expressions")
                    and not query.selects[0].is_star)
                if call.single_column and isinstance(query.selects[0], exp.Alias):
                    call.alias = query.selects[0].args["alias"]
            except SpecError:
                pass  # A resolved SQL fragment need not be a projection expression.
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


def parse_model(project, code, context="SQL", *, expand=False, partial=False):
    """Mask single-column calls, or expand SQL; partial reviews retain opaque boundaries.

    Strict callers (inspection/optimization) still require the complete query.
    Partial placeholders only locate surrounding authored SQL, never output columns.
    """
    calls = classify_calls(project, code, context)
    if not calls:
        return parse_authored(code, project.require_dialect(), context)
    replacements, masks, opaque, aliases = [], {}, {}, {}
    for call in calls:
        unresolved = call.sql is None or not (expand or call.single_column)
        if unresolved and (not partial or call.raw.startswith("{{-") or call.raw.endswith("-}}")):
            raise UnsupportedSQL(call.reason)
        if expand and not unresolved:
            replacement = call.sql
        else:
            token = "extra_macro_" + hashlib.sha256(call.raw.encode()).hexdigest()[:16]
            if token.casefold() in code.casefold():
                raise SpecError("Reserved macro analysis token collision")
            masks[token] = call.raw
            if unresolved:
                opaque[token] = call.reason
            replacement = token + "()"
            if not unresolved and call.alias is not None:
                aliases[token] = call.alias.name
                replacement += " AS " + call.alias.sql(dialect=project.require_dialect())
        replacements.append((call.start, call.end, replacement))
    for start, end, replacement in reversed(replacements):
        code = code[:start] + replacement + code[end:]
    try:
        parsed = parse_authored(code, project.require_dialect(), context)
    except SpecError as exc:
        if opaque:
            raise UnsupportedSQL(f"{context}: unresolved macro output prevents structural SQL analysis; source preserved") from exc
        raise
    if masks:
        uses = {n.name.lower() for n in parsed.tree.find_all(exp.Anonymous)}
        if set(masks) - uses or any(t.name.lower() in masks for t in parsed.tree.find_all(exp.Table)):
            raise UnsupportedSQL("Scalar macros must be used as SQL expressions")
    parsed.macros = masks
    parsed.opaque_macros = opaque
    parsed.macro_aliases = aliases
    return parsed
