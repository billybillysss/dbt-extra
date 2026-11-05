"""Conservative authored-SQL rewrites, returned as checked changes plus skips."""

from collections import Counter

from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from dbt_extra.errors import SpecError
from dbt_extra.files.changes import ChangeSet, digest
from dbt_extra.sql.macros import macro_calls, parse_model
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.qualification import qualify_source, remember_schema_outputs, source_schema
from dbt_extra.sql.renderer import render, sql
from dbt_extra.sql.schema_evidence import SourceSchemas
from dbt_extra.sql.scopes import volatile
from dbt_extra.sql.source_expressions import retained_boundaries, simplify_source_expressions
from dbt_extra.sql.source_rules import (collapse_complementary_union, decorrelate_filter_exists,
                                   generated_aliases, prune_source_projections, redundant_aliases, remember_identifiers,
                                   remember_outputs, restore_identifiers, rewrite_source)


def _optimizer_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (SqlglotError, KeyError) as exc:
        raise SpecError(f"Cannot safely optimize ({type(exc).__name__}: {exc}); verify complete input schemas and SQLGlot compatibility") from exc


def _once(code, dialect, *, schema, pretty, project=None, evidence=None, report=None):
    parse = (lambda text: parse_model(project, text)) if project else (lambda text: parse_authored(text, dialect))
    parsed = parse(code)
    expanded = parse_model(project, code, expand=True) if parsed.macros else parsed
    if volatile(expanded.tree):
        raise SpecError("Volatile or unknown SQL functions prevent source rewriting")
    inputs = evidence.for_parsed(expanded) if evidence else schema
    inputs = _optimizer_call(source_schema, inputs, dialect)
    tree = expanded.tree.copy()
    if not parsed.macros:
        tree = _optimizer_call(decorrelate_filter_exists, tree)
        tree = _optimizer_call(collapse_complementary_union, tree)
        if report is not None and tree != parsed.tree:
            report["rewritten"] = True
    remember_identifiers(tree)
    occupied = {i.name.casefold() for i in tree.find_all(exp.Identifier)}
    for node in tree.find_all(exp.Table, exp.Subquery):
        node.meta["extra_explicit_alias"] = bool(node.args.get("alias"))
    prepared = tree.copy()
    qualified = _optimizer_call(qualify_source, tree, inputs, dialect)
    remember_schema_outputs(qualified, inputs)
    remember_outputs(qualified)
    unnamed = any(not p.output_name and not p.is_star
                   for scope in traverse_scope(tree) for p in scope.expression.selects)
    if unnamed:
        result = parsed.tree.copy() if parsed.macros else prepared
    elif parsed.macros:
        result = _optimizer_call(prune_source_projections, parsed.tree, expanded.tree, qualified)
        result = _optimizer_call(simplify_source_expressions, result, dialect, macros=parsed.macros)
        if report is not None and result != parsed.tree:
            report["rewritten"] = True
    else:
        interface = [p.output_name for p in qualified.selects]
        spelled_interface = [p.output_name for p in restore_identifiers(qualified.copy()).selects]
        pruned = _optimizer_call(prune_source_projections, prepared, prepared, qualified)
        original = qualified.copy()
        if pruned != prepared:
            qualified = _optimizer_call(qualify_source, pruned, inputs, dialect)
            remember_schema_outputs(qualified, inputs)
            remember_outputs(qualified)
        qualified = _optimizer_call(simplify_source_expressions, qualified, dialect, schema=inputs)
        result = _optimizer_call(rewrite_source, qualified, dialect)
        if report is not None and result != original:
            report["rewritten"] = True
        result = _optimizer_call(qualify_source, result, inputs, dialect)
        if [p.output_name for p in result.selects] != interface:
            raise SpecError("Optimization changed the output interface")
        result = redundant_aliases(restore_identifiers(generated_aliases(result, occupied)))
        if [p.output_name for p in result.selects] != spelled_interface:
            raise SpecError("Optimization changed output spelling or order")
    before_comments = sorted(c for n in parsed.tree.walk() for c in n.comments or [])
    after_comments = sorted(c for n in result.walk() for c in n.comments or [])
    if before_comments != after_comments:
        raise SpecError("Rewrite would discard SQL comments")
    candidate = render(result, parsed, dialect, pretty=pretty, prefix=True)
    reparsed = parse(candidate)
    if reparsed.tree != result and sql(reparsed.tree, dialect) != sql(result, dialect):
        raise SpecError("Candidate SQL did not round-trip")
    if parsed.macros:
        validated = _optimizer_call(qualify_source, parse_model(project, candidate, expand=True).tree, inputs, dialect)
        if [p.output_name for p in validated.selects] != [p.output_name for p in qualified.selects]:
            raise SpecError("Optimization changed the output interface")
    elif not unnamed:
        _optimizer_call(qualify_source, reparsed.tree, inputs, dialect)
    if Counter(raw for _, _, raw, _ in macro_calls(code)) != Counter(raw for _, _, raw, _ in macro_calls(candidate)):
        raise SpecError("Rewrite would change authored macro calls")
    return candidate


def _fixed_point(code, dialect, *, schema=None, pretty=True, project=None, evidence=None, report=None):
    seen = {code}
    for _ in range(4):
        candidate = _once(code, dialect, schema=schema, pretty=pretty, project=project, evidence=evidence, report=report)
        if candidate == code:
            return candidate
        if candidate in seen:
            raise SpecError("Source optimization entered a rewrite cycle; model unchanged")
        seen.add(candidate)
        code = candidate
    raise SpecError("Source optimization did not converge within four passes; model unchanged")


def optimize_source(code, dialect, *, schema=None, pretty=True):
    """Rewrite only when bindings, interfaces and a bounded fixed point validate.

    Explicit caller schemas must be complete, ordered relation schemas, not a
    list of documented columns. No warehouse access or metadata guesses occur.
    """
    return _fixed_point(code, dialect, schema=schema, pretty=pretty)


def optimize(project, *, select=None, exclude=None, format="pretty", preserve_macros=True):
    dialect = project.require_dialect()
    if format not in {"pretty", "compact"}:
        raise SpecError("optimization.format must be pretty or compact")
    if not preserve_macros:
        raise SpecError("Optimization always preserves Jinja; macro expansion is not a source rewrite")
    changes, skipped = ChangeSet(project.root), {}
    changes.optimization_report = {}
    evidence = SourceSchemas(project)
    for path, data in project.contents.items():
        # Discovery, schema inference, macros and configuration all share this
        # immutable snapshot. Watch absent artifacts/settings as well as files.
        changes.watch(path, digest(data), check=True, external=not path.is_relative_to(project.root))
    for resource in project.select(select, exclude, kinds={"model"}):
        if not resource.path or resource.path.suffix != ".sql":
            skipped[resource.id] = "Read-only artifact/package or non-SQL model"
            continue
        changes.watch(resource.path, digest(project.contents[resource.path]), check=True)
        report = {}
        try:
            candidate = _fixed_point(resource.code, dialect, pretty=format == "pretty", project=project, evidence=evidence, report=report)
        except SpecError as exc:
            skipped[resource.id] = str(exc)
            continue
        before = parse_model(project, resource.code).tree
        after = parse_model(project, candidate).tree
        if candidate.encode("utf-8") == project.contents[resource.path]:
            status = "unchanged"
        elif before == after:
            status = "formatted"
        else:
            status = "rewritten" if report.get("rewritten") else "qualified"
        changes.set(resource.path, candidate)
        changes.optimization_report[resource.id] = {
            "status": status,
            "formatting_only": status == "formatted",
            "changed": candidate.encode("utf-8") != project.contents[resource.path],
            "retained": retained_boundaries(after),
        }
    return changes, skipped
