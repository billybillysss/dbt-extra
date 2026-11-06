"""Predictable display aliases, without inferring business roles from SQL."""

import hashlib
import re

from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope


ALIAS_TARGET = 30
LAYERS = {"stg", "brz", "slv", "gld"}
ABBREVIATIONS = {"customer": "cust", "customers": "custs", "transaction": "txn",
                 "transactions": "txns", "revenue": "rev", "summary": "sum"}


def short_names():
    index = 0
    while True:
        value, name = index, ""
        while True:
            value, digit = divmod(value, 26)
            name = chr(97 + digit) + name
            if not value:
                break
            value -= 1
        yield name
        index += 1


def generated_aliases(tree, occupied):
    """Rename only generated relation aliases, using native scope bindings."""
    names = short_names()
    occupied = set(occupied)
    for scope in traverse_scope(tree):
        for old, (node, _) in list(scope.selected_sources.items()):
            if not isinstance(node, (exp.Table, exp.Subquery)) or node.meta.get("extra_explicit_alias"):
                continue
            alias = node.args.get("alias")
            if not alias:
                continue
            name = next(names)
            while name in occupied:
                name = next(names)
            occupied.add(name)
            alias.set("this", exp.to_identifier(name))
            for column in scope.columns:
                if column.table == old:
                    column.set("table", exp.to_identifier(name))
    return tree


def redundant_aliases(tree):
    for alias in list(tree.find_all(exp.Alias)):
        column, name = alias.this, alias.args["alias"]
        if (isinstance(column, exp.Column) and not column.is_star
                and column.this == name and not alias.comments):
            alias.replace(column.copy())
    return tree


def readable_name(name):
    normalized = name.casefold()
    prefix, separator, remainder = normalized.partition("_")
    if separator and prefix in LAYERS:
        normalized = remainder
    words = re.findall(r"[a-z0-9]+", normalized)
    words = words or ["input"]
    if words[0][0].isdigit():
        words.insert(0, "input")
    for index in range(len(words)):
        if len("_".join(words)) <= ALIAS_TARGET:
            break
        words[index] = ABBREVIATIONS.get(words[index], words[index])
    result = "_".join(words)
    if len(result) > ALIAS_TARGET:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
        prefix = []
        for word in words:
            if len("_".join([*prefix, word])) > ALIAS_TARGET - 7:
                break
            prefix.append(word)
        result = "_".join(prefix or ["input"]) + "_" + digest
    return result


def available_alias(name, occupied, *, context=None):
    """Callers reserve enclosing names too, avoiding correlated-name capture."""
    occupied = {value.casefold() for value in occupied}
    base = readable_name(name)
    if base in occupied and context:
        base = readable_name(f"{context}_{name}")
    alias, index = base, 2
    while alias.casefold() in occupied:
        alias = f"{base}_{index}"
        index += 1
    return alias
