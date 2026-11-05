"""Validate dbt template structure without evaluating macros or control flow."""

import re

from jinja2 import Environment, TemplateSyntaxError, nodes
from jinja2.ext import Extension

from dbt_extra.errors import SpecError


JINJA = re.compile(r"{{.*?}}|{#.*?#}|{%.*?%}", re.DOTALL)


class DbtBlocks(Extension):
    tags = {"snapshot", "test", "materialization", "docs"}

    def parse(self, parser):
        token = next(parser.stream)
        while not parser.stream.current.test("block_end"):
            if parser.stream.current.test("eof"):
                parser.fail(f"Unterminated {token.value} block", token.lineno)
            next(parser.stream)
        body = parser.parse_statements([f"name:end{token.value}"], drop_needle=True)
        return nodes.Scope(body).set_lineno(token.lineno)


def environment():
    return Environment(extensions=[DbtBlocks, "jinja2.ext.do", "jinja2.ext.loopcontrols"])


def validate_template(code, context="SQL"):
    try:
        return environment().parse(code)
    except TemplateSyntaxError as exc:
        raise SpecError(f"{context}: invalid Jinja: {exc}") from exc


def lex_spans(code):
    """Map Jinja's newline-normalized tokens back to original source offsets."""
    normalized, offsets = [], []
    index = 0
    while index < len(code):
        offsets.append(index)
        char = code[index]
        normalized.append("\n" if char == "\r" else char)
        index += 2 if code[index:index + 2] == "\r\n" else 1
    offsets.append(len(code))
    normalized = "".join(normalized)
    cursor = 0
    for _, kind, value in environment().lex(normalized):
        start = normalized.find(value, cursor)
        if start < 0:
            raise SpecError("Cannot locate authored Jinja token")
        cursor = start + len(value)
        yield kind, value, offsets[start], offsets[cursor]


def macro_blocks(code, context="SQL"):
    """Locate named macro blocks without matching comments, strings or raw text."""
    validate_template(code, context)
    blocks, stack, tag = [], [], []
    for kind, value, start, end in lex_spans(code):
        if kind == "block_begin":
            tag = []
            opening = start
        elif kind == "block_end":
            names = [v for k, v in tag if k == "name"]
            if names and names[0] == "macro":
                stack.append((names[1], opening))
            elif names and names[0] == "endmacro":
                name, beginning = stack.pop()
                if not stack:
                    blocks.append({"name": name, "start": beginning, "end": start + value.index("%}") + 2})
            tag = []
        else:
            tag.append((kind, value))
    return blocks
