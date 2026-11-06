"""Parse authored models using definitions from the project's local snapshot."""

import hashlib

from sqlglot import exp

from dbt_extra.errors import SpecError
from dbt_extra.sql.models import UnsupportedSQL
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.templates.expansion import expand_static
from dbt_extra.sql.templates.macros import classify_calls, macro_calls, macro_definitions


def definitions_for(project):
    return macro_definitions((r.package, r.code, r.source_file) for r in project.resources.values()
                             if r.kind == "macro" and r.path is not None)


def model_macro_calls(project, code, context="SQL"):
    if not macro_calls(code):
        return []
    return classify_calls(code, project.require_dialect(), context,
                          definitions=definitions_for(project), package=project.name)


def parse_model(project, code, context="SQL", *, expand=False, partial=False):
    """Mask scalar calls or expand SQL; partial reviews retain opaque boundaries."""
    template_source = None
    if "{%" in code or "{#" in code:
        template_source, code = code, expand_static(code, context, definitions=definitions_for(project), package=project.name)
    calls = model_macro_calls(project, code, context)
    if not calls:
        parsed = parse_authored(code, project.require_dialect(), context)
        parsed.template_source = template_source if not expand else None
        return parsed
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
    parsed.template_source = template_source if not expand else None
    return parsed
