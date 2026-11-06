"""Layout-only formatting of authored config calls; never evaluate Jinja."""

from jinja2 import nodes

from dbt_extra.errors import SpecError
from dbt_extra.sql.templates.syntax import lex_spans, output_spans, validate_template


def _split(tokens, separator):
    parts, start, depth = [], 0, 0
    for index, (kind, value, _, _) in enumerate(tokens):
        if kind != "operator":
            continue
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")", "]", "}"}:
            depth -= 1
        elif depth == 0 and value == separator:
            parts.append(tokens[start:index])
            start = index + 1
    if start < len(tokens):
        parts.append(tokens[start:])
    return parts


def _text(code, tokens, pretty):
    if not tokens:
        return ""
    if pretty:
        return code[tokens[0][2]:tokens[-1][3]]
    # Normalize only whitespace between tokens, never inside string literals.
    result, last = [], tokens[0][2]
    for _, _, start, end in tokens:
        if start > last:
            result.append(" ")
        result.append(code[start:end])
        last = end
    return "".join(result)


def _value(code, tokens, level, pretty):
    if not tokens or tokens[0][0] != "operator" or tokens[0][1] not in {"[", "{"}:
        return _text(code, tokens, pretty)
    depth = 0
    for index, (kind, value, _, _) in enumerate(tokens):
        if kind == "operator":
            depth += (value in {"(", "[", "{"}) - (value in {")", "]", "}"})
            if depth == 0:
                break
    if index != len(tokens) - 1:
        return _text(code, tokens, pretty)  # A lookup/filter/operator, not a bare container.
    opening, closing = tokens[0][1], tokens[-1][1]
    entries = []
    for part in _split(tokens[1:-1], ","):
        if opening == "{":
            pair = _split(part, ":")
            if len(pair) != 2:
                return _text(code, tokens, pretty)
            entries.append(_text(code, pair[0], pretty) + ": " + _value(code, pair[1], level + 1, pretty))
        else:
            entries.append(_value(code, part, level + 1, pretty))
    return _layout(opening, closing, entries, level, pretty)


def _layout(opening, closing, entries, level, pretty):
    if not entries:
        return opening + closing
    if not pretty:
        return opening + ", ".join(entries) + closing
    indent = "    " * (level + 1)
    return opening + "\n" + indent + (",\n" + indent).join(entries) + "\n" + "    " * level + closing


def _call(raw, pretty):
    if raw.startswith("{{-") or raw.endswith("-}}"):
        return raw
    tokens = [token for token in lex_spans(raw) if token[0] not in {"whitespace", "variable_begin", "variable_end"}]
    if [token[1] for token in tokens[:2]] != ["config", "("] or tokens[-1][1] != ")":
        return raw
    entries = []
    for part in _split(tokens[2:-1], ","):
        pair = _split(part, "=")
        if len(pair) == 2 and len(pair[0]) == 1 and pair[0][0][0] == "name":
            entries.append(pair[0][0][1] + "=" + _value(raw, pair[1], 1, pretty))
        else:
            entries.append(_value(raw, part, 1, pretty))
    candidate = "{{ " + _layout("config(", ")", entries, 0, pretty) + " }}"
    # Node equality compares semantic fields, not source line numbers.
    if validate_template(raw) != validate_template(candidate):
        return raw
    return candidate


def format_configs(code, *, pretty=True):
    """Format only config output tags; preserve all other authored text verbatim."""
    pieces, last = [], 0
    for start, end, raw, node in output_spans(code):
        if not (isinstance(node, nodes.Call) and isinstance(node.node, nodes.Name) and node.node.name == "config"):
            continue
        try:
            candidate = _call(raw, pretty)
        except SpecError:
            candidate = raw
        pieces.extend((code[last:start], candidate))
        last = end
    return "".join(pieces) + code[last:]
