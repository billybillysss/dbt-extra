"""Read-only SQL parsing and reversible masking of literal dbt references."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from jinja2 import TemplateSyntaxError, nodes
from sqlglot import exp, parse
from sqlglot.errors import ErrorLevel, SqlglotError

from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import text
from dbt_extra.sql.functions import recognize_functions
from dbt_extra.sql.jinja import JINJA, environment, validate_template
from dbt_extra.sql.references import Reference


class UnsupportedSQL(SpecError):
    """Valid template structure that cannot be analyzed without rendering dbt."""


@dataclass
class Parsed:
    tree: exp.Query
    refs: dict[str, Reference] = field(default_factory=dict)
    prefix: str = ""
    config: dict = field(default_factory=dict)
    config_dynamic: bool = False
    macros: dict[str, str] = field(default_factory=dict)
    opaque_macros: dict[str, str] = field(default_factory=dict)
    macro_aliases: dict[str, str] = field(default_factory=dict)


def read_query(value: str, context: str, dialect) -> exp.Query:
    text(value, context)
    if any(marker in value for marker in ("{{", "{%", "{#")):
        raise SpecError(f"{context}: unmasked Jinja is not valid static SQL")
    try:
        statements = parse(value, read=dialect, error_level=ErrorLevel.RAISE)
        if len(statements) != 1 or statements[0] is None:
            raise SpecError(f"{context}: expected one SQL statement")
        tree = statements[0]
    except SqlglotError as exc:
        # sqlglot highlights failures with terminal escapes, which are illegal
        # XML characters in XLSX review diagnostics.
        message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
        raise SpecError(f"{context}: invalid {dialect} SQL: {message}") from exc
    if not isinstance(tree, exp.Query) or any(isinstance(n, (exp.DDL, exp.DML, exp.Command, exp.Into, exp.Lock)) for n in tree.walk()):
        raise SpecError(f"{context}: SQL must be one read-only query")
    for node in tree.find_all(exp.SetOperation):
        if len(node.this.selects) != len(node.expression.selects):
            raise SpecError(f"{context}: set-operation branches must have matching column counts")
    return recognize_functions(tree, dialect)


def parse_authored(code, dialect, context="SQL"):
    """Mask static config/ref/source/this constructs; never evaluate templates."""
    validate_template(code, context)
    refs, configs = {}, {}
    config_dynamic = False
    prefix_end = 0
    segments, last = [], 0
    for match in JINJA.finditer(code):
        raw = match.group()
        if raw.startswith(("{%", "{#")):
            raise UnsupportedSQL(f"{context}: dynamic Jinja blocks/comments are preserved; SQL rewriting unavailable")
        if raw.startswith("{{-") or raw.endswith("-}}"):
            raise UnsupportedSQL(f"{context}: Jinja whitespace-control expressions are preserved")
        try:
            template = environment().parse(raw)
        except TemplateSyntaxError as exc:
            raise UnsupportedSQL(f"{context}: complex Jinja delimiters are preserved; source rewriting unavailable") from exc
        output = template.body[0]
        expression = output.nodes[0] if isinstance(output, nodes.Output) and len(output.nodes) == 1 else None
        if isinstance(expression, nodes.Call) and isinstance(expression.node, nodes.Name):
            name = expression.node.name
        elif isinstance(expression, nodes.Name) and expression.name == "this":
            name = "this"
        else:
            raise UnsupportedSQL(f"{context}: opaque Jinja expression {raw}; source unchanged")
        if name == "config":
            preceding = re.sub(r"/\*.*?\*/|--[^\r\n]*", "", code[prefix_end:match.start()], flags=re.DOTALL)
            if preceding.strip():
                raise UnsupportedSQL(f"{context}: config must precede SQL for source rewriting")
            prefix_end = match.end()
            config_dynamic |= bool(expression.args or expression.dyn_args or expression.dyn_kwargs)
            for kw in expression.kwargs:
                try:
                    configs[kw.key] = kw.value.as_const()
                except nodes.Impossible:
                    config_dynamic = True
            # Preserve header comments/config once, outside the SQL tree.
            segments.clear()
            last = match.end()
            continue
        elif name in {"ref", "source", "this"}:
            args = expression.args if isinstance(expression, nodes.Call) else []
            kwargs = expression.kwargs if isinstance(expression, nodes.Call) else []
            if any(not isinstance(a, nodes.Const) or not isinstance(a.value, str) for a in args):
                raise UnsupportedSQL(f"{context}: dynamic {name} arguments are preserved")
            if isinstance(expression, nodes.Call) and (expression.dyn_args or expression.dyn_kwargs):
                raise UnsupportedSQL(f"{context}: dynamic {name} arguments are preserved")
            if name == "ref" and len(args) not in {1, 2} or name == "source" and len(args) != 2:
                raise UnsupportedSQL(f"{context}: unsupported {name} arguments")
            version = None
            for kw in kwargs:
                if name != "ref" or kw.key not in {"v", "version"} or not isinstance(kw.value, nodes.Const):
                    raise UnsupportedSQL(f"{context}: unsupported {name} keyword arguments")
                version = kw.value.value
            token = "extra_ref_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
            if token.casefold() in code.casefold():
                raise SpecError(f"{context}: reserved analysis token collision")
            refs[token] = Reference(raw, name, tuple(a.value for a in args), version)
            replacement = token
        else:
            raise UnsupportedSQL(f"{context}: opaque macro {name}; source unchanged")
        segments.extend((code[last:match.start()], replacement))
        last = match.end()
    segments.append(code[last:])
    tree = read_query("".join(segments), context, dialect)
    if any(w.args.get("recursive") for w in tree.find_all(exp.With)):
        raise UnsupportedSQL(f"{context}: recursive SQL is preserved")
    for token in refs:
        identifiers = [i for i in tree.find_all(exp.Identifier) if i.name == token]
        if not identifiers or any(not isinstance(i.parent, exp.Table) or i.arg_key != "this" for i in identifiers):
            raise UnsupportedSQL(f"{context}: dbt references must be standalone SQL relation inputs")
        for identifier in identifiers:
            identifier.set("quoted", True)
    return Parsed(tree, refs, code[:prefix_end], configs, config_dynamic)
