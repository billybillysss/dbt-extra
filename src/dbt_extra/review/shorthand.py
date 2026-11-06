"""Reversible review-only spelling of simple dbt template calls."""

import re

from jinja2 import nodes

from dbt_extra.errors import SpecError
from dbt_extra.sql.templates.syntax import call_name, output_spans, validate_template


IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]*"
PATH = re.compile(IDENTIFIER + r"(?:\." + IDENTIFIER + r")*")


def literal(node):
    return (isinstance(node, nodes.Const)
            or isinstance(node, (nodes.List, nodes.Tuple)) and all(literal(item) for item in node.items))


def simple_call(node):
    return (isinstance(node, nodes.Call) and call_name(node.node)
            and not node.dyn_args and not node.dyn_kwargs
            and all(literal(a) for a in node.args)
            and all(literal(k.value) for k in node.kwargs))


def short_call(raw, node):
    if raw.startswith("{{-") or raw.endswith("-}}") or not simple_call(node):
        return raw
    name = call_name(node.node)
    if name in {"ref", "source"}:
        if not all(isinstance(a, nodes.Const) for a in node.args):
            return raw
        args = [a.value for a in node.args]
        valid = len(args) in {1, 2} if name == "ref" else len(args) == 2
        if valid and not node.kwargs and all(isinstance(a, str) and re.fullmatch(IDENTIFIER, a) for a in args):
            return ".".join([name, *args])
        return raw  # Versioned/dynamic references retain their exact syntax.
    if name in {"config", "return", "var", "env_var"}:
        return raw
    return "macro." + raw[2:-2].strip()


def protected_end(code, start):
    """Skip SQL literals/identifiers/comments and existing Jinja as single units."""
    dollar = re.match(r"\$(?:[A-Za-z_]\w*)?\$", code[start:]) if code[start] == "$" else None
    if dollar:
        delimiter = dollar.group()
        end = code.find(delimiter, start + len(delimiter))
        return len(code) if end < 0 else end + len(delimiter)
    if code.startswith(("{{", "{%", "{#"), start):
        closer = {"{{": "}}", "{%": "%}", "{#": "#}"}[code[start:start + 2]]
        quote, index = None, start + 2
        while index < len(code):
            char = code[index]
            if quote:
                if char == "\\":
                    index += 2
                    continue
                if char == quote:
                    quote = None
            elif code.startswith(closer, index):
                end = index + 2
                if code[start:start + 2] == "{%" and code[start:end].strip("{%}- \n\t") == "raw":
                    match = re.search(r"{%\s*-?\s*endraw\s*-?\s*%}", code[end:])
                    return end + match.end() if match else len(code)
                return end
            elif char in "\"'" and closer != "#}":
                quote = char
            index += 1
        return len(code)
    if code.startswith("--", start):
        end = code.find("\n", start)
        return len(code) if end < 0 else end
    if code.startswith("/*", start):
        depth, index = 1, start + 2
        while index < len(code) and depth:
            if code.startswith("/*", index):
                depth += 1
                index += 2
            elif code.startswith("*/", index):
                depth -= 1
                index += 2
            else:
                index += 1
        return index
    if code[start] in "'\"`[":
        closer = "]" if code[start] == "[" else code[start]
        index = start + 1
        while index < len(code):
            if code[index] == closer:
                if code[index:index + 2] == closer * 2:
                    index += 2
                    continue
                return index + 1
            if code[index] == "\\":
                index += 1
            index += 1
        return len(code)
    return start


def display(code):
    replacements = {start: (end, short_call(raw, node)) for start, end, raw, node in output_spans(code)}
    result, index = [], 0
    while index < len(code):
        end = protected_end(code, index)
        if index in replacements:
            end, value = replacements[index]
            result.append(value)
        elif end > index:
            result.append(code[index:end])
        else:
            end = index + 1
            result.append(code[index:end])
        index = end
    return "".join(result)


def restore(code, original=""):
    """Restore unchanged calls verbatim; new shorthand becomes validated Jinja."""
    originals = {short_call(raw, node): raw for _, _, raw, node in output_spans(original)}
    native, position = set(), 0
    while position < len(original):
        stop = protected_end(original, position)
        if stop > position:
            position = stop
            continue
        match = PATH.match(original, position)
        if match:
            native.add(match.group())
            position = match.end()
        else:
            position += 1
    result, index = [], 0
    while index < len(code):
        end = protected_end(code, index)
        if end > index:
            result.append(code[index:end])
            index = end
            continue
        match = PATH.match(code, index) if index == 0 or not re.match(r"[\w.]", code[index - 1]) else None
        token = match.group() if match else ""
        end = match.end() if match else index + 1
        raw = None
        parts = token.split(".")
        if token in native:
            pass  # Existing SQL qualifiers are not newly introduced shorthand.
        elif parts[0] in {"ref", "source"} and len(parts) in ({2, 3} if parts[0] == "ref" else {3}):
            raw = "{{ " + parts[0] + "(" + ", ".join(repr(p) for p in parts[1:]) + ") }}"
        elif token.startswith("macro.") and code[end:end + 1] == "(":
            depth, cursor = 1, end + 1
            while cursor < len(code) and depth:
                stop = protected_end(code, cursor)
                if stop > cursor:
                    cursor = stop
                    continue
                depth += (code[cursor] == "(") - (code[cursor] == ")")
                cursor += 1
            if depth:
                raise SpecError("Unclosed macro shorthand call")
            end = cursor
            raw = "{{ " + code[index + len("macro."):end] + " }}"
            template = validate_template(raw)
            if not simple_call(template.body[0].nodes[0]):
                raise SpecError("Use original Jinja for complex macro arguments")
        if raw:
            result.append(originals.get(code[index:end], raw))
        else:
            result.append(code[index:end])
        index = end
    return "".join(result)
