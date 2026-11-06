"""Bounded, allowlisted interpretation of local SQL-generating macros.

No Python/Jinja execution, adapter access, dbt invocation or warehouse calls.
Unknown constructs stay opaque rather than guessing their output shape.
"""

from jinja2 import nodes

from dbt_extra.sql.models import UnsupportedSQL
from dbt_extra.sql.templates.syntax import call_name


LIMIT = 100000


class StaticMacros:
    def __init__(self, definitions=None, *, package="static"):
        self.package = package
        self.definitions = definitions or {}
        self.budget = 10000

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
        if isinstance(node, nodes.Getattr) and node.attr in {"upper", "lower", "strip"}:
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
        if isinstance(call.node, nodes.Getattr) and call.node.attr in {"upper", "lower", "strip"}:
            if call.args or call.kwargs or call.dyn_args or call.dyn_kwargs:
                raise UnsupportedSQL("String methods require no arguments")
            value = self.value(call.node.node, values or {}, active)
            if not isinstance(value, str):
                raise UnsupportedSQL("String methods require a static string")
            operation = {"upper": str.upper, "lower": str.lower, "strip": str.strip}[call.node.attr]
            return self.checked(operation(value))
        name = call_name(call.node)
        if not name or call.dyn_args or call.dyn_kwargs:
            raise UnsupportedSQL("Dynamic macro invocation remains opaque")
        if name in {"ref", "source", "config", "var", "env_var", "return"}:
            raise UnsupportedSQL(f"dbt context call {name} remains opaque inside macros")
        package = active[-1].rsplit(".", 1)[0] if active else self.package
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
                if type(condition) is not bool:
                    raise UnsupportedSQL("Macro conditions require static booleans")
                branch = node.body if condition else node.else_
                if not condition:
                    for alternative in node.elif_:
                        decision = self.value(alternative.test, values, active)
                        if type(decision) is not bool:
                            raise UnsupportedSQL("Macro conditions require static booleans")
                        if decision:
                            branch = alternative.body
                            break
                output.append(self.body(branch, values, active))
            else:
                raise UnsupportedSQL(f"Static macro expansion unavailable for {type(node).__name__}")
            self.checked("".join(output))
        return "".join(output)

