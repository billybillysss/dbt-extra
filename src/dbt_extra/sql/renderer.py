"""Dialect-aware SQL rendering with authored dbt references restored."""

import re

from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError

from dbt_extra.errors import SpecError
from dbt_extra.sql.templates.config_format import format_configs
from dbt_extra.sql.aliases import available_alias


def sql(node, dialect, *, pretty=False):
    try:
        return node.sql(dialect=dialect, pretty=pretty, unsupported_level=ErrorLevel.RAISE)
    except SqlglotError as exc:
        raise SpecError(f"unsupported {dialect} SQL: {exc}") from exc


def reference_aliases(tree, refs):
    """Keep internal mask identifiers out of rewritten authored aliases."""
    occupied = {i.name.casefold() for i in tree.find_all(exp.Identifier)}
    for token, ref in sorted(refs.items(), key=lambda item: (item[1].kind, item[1].args, str(item[1].version))):
        uses = [i for i in tree.find_all(exp.Identifier) if i.name.casefold() == token.casefold()
                 and not (isinstance(i.parent, exp.Table) and i.arg_key == "this")]
        if not uses:
            continue
        name = ref.args[-1] if ref.args else "stored_self"
        context = ref.args[0] if len(ref.args) > 1 else None
        alias = available_alias(name, occupied, context=context)
        occupied.add(alias)
        for table in tree.find_all(exp.Table):
            if table.name == token and not table.args.get("alias"):
                table.set("alias", exp.TableAlias(this=exp.to_identifier(alias, quoted=True)))
        for identifier in uses:
            identifier.set("this", alias)
            identifier.set("quoted", True)
        if len(name) > 30:
            for subquery in tree.find_all(exp.Subquery):
                if subquery.alias == alias:
                    comment = f" Expanded from: {name} "
                    if comment not in (subquery.comments or []):
                        subquery.add_comments([comment])


def render(tree, parsed, dialect, *, pretty=True, prefix=False, format_config=False, terminate=True):
    if parsed.template_source is not None:
        if tree != parsed.tree:
            raise SpecError("Authored top-level template structure cannot be reconstructed after SQL edits")
        return parsed.template_source
    tree = tree.copy()
    reference_aliases(tree, parsed.refs)
    # Restore templates only in table positions, never aliases or literals.
    replacements = {}
    occupied_text = (sql(tree, dialect) + parsed.prefix + "".join(r.text for r in parsed.refs.values()) + "".join(parsed.macros.values())).casefold()
    for index, function in enumerate(list(tree.find_all(exp.Anonymous))):
        raw = parsed.macros.get(function.name.lower())
        if raw is not None:
            marker = f"EXTRA_RENDER_MACRO_{index}"
            while marker.casefold() in occupied_text:
                marker += "_"
            occupied_text += marker.casefold()
            parent = function.parent
            if function is tree:
                tree = exp.column(marker)
            elif (isinstance(parent, exp.Alias) and parent.this is function
                    and parsed.macro_aliases.get(function.name.lower()) == parent.alias):
                parent.replace(exp.column(marker))
            else:
                function.replace(exp.column(marker))
            replacements[marker] = raw
    for index, table in enumerate(tree.find_all(exp.Table)):
        ref = parsed.refs.get(table.name)
        if ref:
            if not table.args.get("alias") and any(c.table == table.name for c in tree.find_all(exp.Column)):
                table.set("alias", exp.TableAlias(this=exp.to_identifier(table.name)))
            marker = f"EXTRA_RENDER_RELATION_{index}"
            while marker.casefold() in occupied_text:
                marker += "_"
            occupied_text += marker.casefold()
            table.set("this", exp.to_identifier(marker))
            replacements[marker] = ref.text
    rendered = sql(tree, dialect, pretty=pretty)
    for marker, raw in replacements.items():
        rendered = re.sub(rf'(?<![\w])(?:"{marker}"|`{marker}`|\[{marker}\]|{marker})(?![\w])', lambda _: raw, rendered)
    header = parsed.prefix
    if format_config and prefix and header:
        header = format_configs(header, pretty=pretty)
    header = header + "\n\n" if prefix and header else ""
    # dbt embeds model SQL inside materialization queries. A statement terminator
    # is valid for standalone inspection, but not inside those wrappers.
    return header + rendered + (";\n" if terminate else "\n")
