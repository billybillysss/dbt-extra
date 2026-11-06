"""dbt-native command orchestration; no dbt or warehouse execution."""

from functools import wraps
from pathlib import Path
from zipfile import BadZipFile

import click
from sqlglot.errors import SqlglotError

from dbt_extra import __version__
from dbt_extra.config import resolve_project
from dbt_extra.enrichment import enrich
from dbt_extra.files.changes import ChangeSet
from dbt_extra.files.paths import safe_path
from dbt_extra.project import Project
from dbt_extra.review import export_review, import_review
from dbt_extra.inspection import inspect, plan
from dbt_extra.optimization import optimize
from dbt_extra.sql.renderer import render
from dbt_extra.sql.rewrites.session import outcome_text
from dbt_extra.validation import validate as validate_project
from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import dump_yaml


class Names(click.Option):
    """A repeatable option accepting one or more space-separated selectors."""
    def __init__(self, *args, **kwargs):
        kwargs["type"] = click.UNPROCESSED
        super().__init__(*args, **kwargs)

    def add_to_parser(self, parser, ctx):
        super().add_to_parser(parser, ctx)
        option = next((parser._long_opt.get(name) or parser._short_opt.get(name) for name in self.opts
                       if parser._long_opt.get(name) or parser._short_opt.get(name)), None)
        original = option.process
        def process(value, state):
            values = [value]
            while state.rargs and not state.rargs[0].startswith("-"):
                values.append(state.rargs.pop(0))
            original(tuple(values), state)
        option.process = process


def names(values):
    return [name for group in values for name in group] if values else None


def guarded(function):
    @wraps(function)
    def run(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, UnicodeError, BadZipFile, SqlglotError) as exc:
            raise click.ClickException(str(exc)) from exc
    return run


def loaded(ctx, dialect=None):
    return Project(ctx.obj["directory"], dialect=dialect or ctx.obj["dialect"], manifest=ctx.obj["manifest"])


def selectors(function):
    function = click.option("--exclude", cls=Names, multiple=True, help="Selectors to exclude; explicit lists replace configuration.")(function)
    return click.option("--select", "-s", cls=Names, multiple=True, help="Names, resource IDs, or path:/tag:/package:/resource_type: selectors.")(function)


def preview_option(function):
    return click.option("--preview", is_flag=True, help="Show proposed changes without writing files.")(function)


def summary(changes, preview):
    for path in changes:
        click.echo(f"update: {path}")
    click.echo(f"{'Preview: ' if preview else ''}{len(changes)} file change(s)")


def finish(changes, preview):
    if preview:
        click.echo(changes.diffs(), nl=False)
    summary(changes.apply(preview=preview), preview)


@click.group()
@click.version_option(version=__version__, prog_name="extra")
@click.option("--project-dir", type=click.Path(path_type=Path), envvar=["EXTRA_PROJECT_DIR", "DBT_PROJECT_DIR"],
              help="dbt project root; overrides EXTRA_PROJECT_DIR, then DBT_PROJECT_DIR, otherwise discover upward from the current directory.")
@click.option("--dialect", help="SQL dialect; overrides configuration and manifest adapter.")
@click.option("--manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Optional dbt manifest evidence; relative to the current directory.")
@click.pass_context
def cli(ctx, project_dir, dialect, manifest):
    """Review, inspect, and edit native dbt transformations offline."""
    ctx.obj = {"directory": project_dir, "dialect": dialect, "manifest": manifest}


@cli.command("init")
@preview_option
@click.pass_context
@guarded
def init_command(ctx, preview):
    """Add optional dbt-extra settings to an existing native dbt project."""
    root = resolve_project(ctx.obj["directory"])
    path = root / "extra_project.yaml"
    safe_path(path)
    if path.exists():
        raise SpecError(f"Refusing to overwrite {path}")
    changes = ChangeSet(root)
    changes.set(path, dump_yaml({"version": 2, "analysis": {"dialect": ctx.obj["dialect"] or "auto"},
        "export": {"output_dir": "extra/review", "format": "xlsx"}, "optimization": {"format": "pretty", "expand": False}}))
    finish(changes, preview)


@cli.command()
@click.option("--dialect")
@click.pass_context
@guarded
def validate(ctx, dialect):
    """Check local structure, static SQL, and reference cycles; never run dbt."""
    project = loaded(ctx, dialect)
    skipped = validate_project(project)
    for uid, reason in skipped.items():
        click.echo(f"Unavailable {uid}: {reason}", err=True)
    click.echo(f"Validated {len(project.resources)} dbt resources offline; {len(skipped)} SQL analysis unavailable. Not a dbt parse/build.")


@cli.command("inspect")
@click.argument("table")
@click.option("--columns", cls=Names, multiple=True)
@click.option("--from", "from_tables", cls=Names, multiple=True, help="Upstream models to retain as relation boundaries.")
@click.option("--optimize", "optimized", type=click.BOOL, default=None)
@click.option("--expand", type=click.BOOL, default=None, help="Expand upstream models and statically resolvable local macros.")
@click.option("--compile", "compiled", type=click.BOOL, default=None, help="Resolve physical relation names offline (default: true); does not run dbt compile.")
@click.option("--view", type=click.Choice(["sql", "plan"]), default="sql")
@click.option("--dialect")
@click.pass_context
@guarded
def inspect_command(ctx, table, columns, from_tables, optimized, expand, compiled, view, dialect):
    """Explain full model or selected-column logic without changing files."""
    project = loaded(ctx, dialect)
    settings = project.options("inspection", {"optimize": optimized, "expand": expand, "compile": compiled, "boundaries": names(from_tables)})
    tree, parsed, issues = inspect(project, table, names(columns), boundaries=settings.get("boundaries", []),
        expanded=settings.get("expand", True), optimized=settings.get("optimize", True), compiled=settings.get("compile", True))
    click.echo("-- Definition explanation, not stored-relation equivalence or a warehouse execution plan.")
    click.echo("-- Offline relation resolution; unresolved dbt templates retained. Not executed. Authored files unchanged."
               if settings.get("compile", True) else "-- Authored dbt ref/source boundaries retained; not executed. Authored files unchanged.")
    for issue in issues:
        if issue.get("status") == "not_applicable":
            continue
        text = outcome_text(issue) if "rule" in issue else issue["reason"]
        click.echo(f"-- Boundary/coverage: {issue['resource_id']}: {text}".replace("\n", " "))
    click.echo(plan(tree, parsed, project.dialect) if view == "plan" else render(tree, parsed, project.dialect), nl=view == "plan")


@cli.command("export")
@click.option("--format", type=click.Choice(["xlsx", "csv", "json"]))
@click.option("--output-dir", "--path", type=click.Path(path_type=Path), help="Review destination; relative to the dbt project root unless absolute.")
@click.option("--view", help="Named view from export.views.")
@click.option("--expand/--no-expand", default=None, help="Show read-only SQL/columns from statically resolvable local macros.")
@selectors
@preview_option
@click.option("--dialect")
@click.pass_context
@guarded
def export_command(ctx, format, output_dir, view, expand, select, exclude, preview, dialect):
    """Export tabular XLSX/CSV review or a read-only JSON analysis catalog."""
    project = loaded(ctx, dialect)
    options = project.options("export", {"format": format, "output_dir": output_dir, "select": names(select), "exclude": names(exclude), "expand": expand}, view=view)
    paths, coverage = export_review(project, format=options.get("format", "xlsx"), output_dir=options.get("output_dir"),
        select=options.get("select"), exclude=options.get("exclude"), preview=preview, expand=options.get("expand", False))
    summary(paths, preview)
    click.echo("Coverage: " + ", ".join(f"{k}={v}" for k, v in coverage.items()))


@cli.command("import")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@preview_option
@click.option("--dialect")
@click.pass_context
@guarded
def import_command(ctx, path, preview, dialect):
    """Apply supported XLSX/CSV edits to their original native dbt files."""
    project = loaded(ctx, dialect)
    changes = import_review(project, path)
    for uid, reason in changes.metadata_skipped.items():
        click.echo(f"Skipped metadata {uid}: {reason}", err=True)
    finish(changes, preview)


@cli.command("optimize")
@selectors
@click.option("--format", type=click.Choice(["pretty", "compact"]))
@click.option("--expand", type=click.BOOL, default=None, help="Write statically resolvable local macros as SQL (default: false).")
@click.option("--enrich", "enrich_enabled", type=click.BOOL, default=None)
@preview_option
@click.option("--dialect")
@click.pass_context
@guarded
def optimize_command(ctx, select, exclude, format, expand, enrich_enabled, preview, dialect):
    """Conservatively rewrite authored dbt SQL, never compiled SQL."""
    project = loaded(ctx, dialect)
    options = project.options("optimization", {"select": names(select), "exclude": names(exclude), "format": format,
        "expand": expand, "enrich": enrich_enabled})
    changes, skipped = optimize(project, select=options.get("select"), exclude=options.get("exclude"),
        format=options.get("format", "pretty"), expand=options.get("expand", False))
    for uid, reason in skipped.items():
        click.echo(f"Skipped {uid}: {reason}. Model unchanged.", err=True)
    optimization_report = changes.optimization_report
    counts = {status: sum(r["status"] == status for r in optimization_report.values())
              for status in ("rewritten", "qualified", "formatted", "unchanged")}
    click.echo(f"Optimization: {len(optimization_report)} accepted "
               f"({counts['rewritten']} structurally rewritten, {counts['qualified']} qualified, "
               f"{counts['formatted']} formatting-only, {counts['unchanged']} unchanged); "
                f"{sum(r['changed'] for r in optimization_report.values())} proposed SQL change(s); {len(skipped)} skipped")
    for uid, report in optimization_report.items():
        for item in report.get("outcomes", []):
            if item["status"] != "not_applicable":
                click.echo(f"Optimization {uid}: {outcome_text(item)}".replace("\n", " "))
        for reason in report["retained"]:
            click.echo(f"Retained {uid}: {reason}")
    if options.get("enrich", False):
        changes, report = enrich(project, select=options.get("select"), exclude=options.get("exclude"), changes=changes)
        enrichment_summary(report)
    finish(changes, preview)
    click.echo(f"Optimization SQL files written: {0 if preview else sum(r['changed'] for r in optimization_report.values())}")


def enrichment_summary(report):
    click.echo(f"Metadata: {sum('value' in r for r in report)} missing properties inferred; {sum('reason' in r for r in report)} unresolved")
    for item in report:
        if "reason" in item and "column" not in item:
            click.echo(f"Skipped metadata {item['resource_id']}: {item['reason']}", err=True)


@cli.command("enrich")
@selectors
@preview_option
@click.option("--dialect")
@click.pass_context
@guarded
def enrich_command(ctx, select, exclude, preview, dialect):
    """Fill missing inferred types and safe passthrough descriptions in dbt YAML."""
    project = loaded(ctx, dialect)
    options = project.options("metadata", {"select": names(select), "exclude": names(exclude)})
    changes, report = enrich(project, select=options.get("select"), exclude=options.get("exclude"))
    enrichment_summary(report)
    finish(changes, preview)


def main(argv=None):
    return cli.main(args=argv, prog_name="extra")
