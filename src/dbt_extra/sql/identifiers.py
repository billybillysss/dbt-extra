"""Preserve authored identifier and output spelling across qualification."""

from sqlglot import exp


def remember_identifiers(tree):
    for identifier in tree.find_all(exp.Identifier):
        identifier.meta["extra_spelling"] = dict(identifier.args)


def remember_outputs(tree):
    # Qualification synthesizes aliases from normalized column names.
    for alias in tree.find_all(exp.Alias):
        identifier = alias.args["alias"]
        if ("extra_spelling" not in identifier.meta and isinstance(alias.this, exp.Column)
                and identifier.name == alias.this.name):
            spelling = alias.this.this.meta.get("extra_spelling")
            if spelling:
                identifier.meta["extra_spelling"] = spelling


def restore_identifiers(tree):
    for identifier in tree.find_all(exp.Identifier):
        spelling = identifier.meta.get("extra_spelling")
        if spelling:
            identifier.set("this", spelling["this"])
            identifier.set("quoted", spelling.get("quoted", False))
    return tree
