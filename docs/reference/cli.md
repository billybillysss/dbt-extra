# CLI reference

```text
extra [OPTIONS] COMMAND [COMMAND_OPTIONS]
```

`python -m dbt_extra` runs the same CLI. Use `extra --help` or
`extra COMMAND --help` for command help. Help and `extra --version` need no project.
dbt-extra never runs dbt or connects to a warehouse.

## Global options

Global options go **before** the command.

| Option | Meaning |
| --- | --- |
| `--project-dir PATH` | Directory containing `dbt_project.yml` |
| `--dialect DIALECT` | SQLGlot dialect name; overrides settings and manifest adapter |
| `--manifest PATH` | Existing manifest file, relative to the current directory |
| `--version` | Print the installed version and exit |
| `--help` | Show help and exit |

Project selection is `--project-dir` > `EXTRA_PROJECT_DIR` > `DBT_PROJECT_DIR` >
nearest `dbt_project.yml` upward from the current directory. Explicit directories
must contain that file; they do not search parents or fall back to another root.
Optional `extra_project.yaml` is loaded beside it.

Input paths and relative project environment variables use the current directory.
Configured paths and export destinations use the project root. Absolute paths
stay absolute. See [configuration](configuration.md#relative-paths).

## Shared command options

| Option | Commands | Behavior |
| --- | --- | --- |
| `--preview` | `init`, `export`, `import`, `optimize`, `enrich` | Show outputs or source diffs; create no files, directories or temporary files |
| `--dialect DIALECT` | All except `init` | Override the global dialect for this command |
| `--select/-s VALUE...` | `export`, `optimize`, `enrich` | Repeatable inclusion list |
| `--exclude VALUE...` | `export`, `optimize`, `enrich` | Repeatable exclusion list |
| `--help` | All | Show command help |

Omitted options use settings, then defaults. Explicit selection lists replace
configured lists rather than append to them.

## Select resources

```bash
extra export --select orders customers --preview
extra export --select 'path:models/gld/**' --exclude macro_revenue --preview
extra export --select 'tag:finance' --preview
extra optimize --select model.jaffle_shop.customer_revenue --preview
```

| Form | Matches |
| --- | --- |
| `orders`, `gld_*` | Resource name or exact resource ID |
| `name:PATTERN` | Name |
| `id:PATTERN` | Resource ID |
| `path:PATTERN` | Project-relative source file path, including filename |
| `tag:PATTERN` | Resource tags |
| `package:PATTERN` | Owning dbt project/package |
| `resource_type:PATTERN` | Resource kind, such as `model`, `source`, `seed`, `snapshot`, `macro`, `macro_definition` or `source_group` |

Patterns are case-sensitive globs; quote them to prevent shell expansion. Multiple
inclusions are a union, then exclusions are removed. Without a selection,
commands consider all eligible resources. A nonempty selection matching nothing
is an error. `optimize` and `enrich` consider models only.

This is a subset of dbt selection: graph operators and intersections are not
supported. Selection does not automatically include upstream definitions in an
export. Use explicit resource IDs to distinguish same-named resources.

## Init

```bash
extra --dialect snowflake init --preview
```

Requires an existing `dbt_project.yml`. Remove `--preview` to create
`extra_project.yaml`; existing settings are never overwritten. There is no
positional directory argument. From outside the project, use
`extra --project-dir PATH --dialect snowflake init --preview`.

## Validate

```bash
extra validate
```

Checks resource discovery, local SQL-file Jinja structure, supported static model
SQL and reference cycles. SQL analysis that is unavailable is printed with a
reason. No selection option is provided: validation considers the loaded project.
This does not run `dbt parse`, `dbt compile`, `dbt build`, data tests, warehouse SQL
validation or enforced-contract checks.

## Inspect

```bash
extra inspect customer_revenue --columns revenue --from orders --compile false
extra inspect customer_revenue --columns revenue --view plan --compile false
extra inspect customer_revenue --copy --output extra/sql/customer_revenue.sql
```

`MODEL` is a model name or exact resource ID.

| Option | Default | Meaning |
| --- | --- | --- |
| `--columns NAME...` | All outputs | Repeated or multiple selected outputs |
| `--from MODEL...` | No explicit boundaries | Repeated or multiple upstream models to retain as inputs; overrides `inspection.boundaries` |
| `--expand true\|false` | `true` | Expand supported upstream models and static local macros |
| `--optimize true\|false` | `true` | Simplify the logical explanation |
| `--compile true\|false` | `true` | Resolve available physical relation names offline |
| `--view sql\|plan` | `sql` | Render SQL or a logical tree |
| `--verbose` | Off | Show full per-rule/per-scope boundary and rewrite diagnostics |
| `--copy` | Off | Copy SQL only to the system clipboard; requires `--view sql` |
| `--output PATH` | None | Save UTF-8 SQL, relative to the dbt project root unless absolute; requires `--view sql` |
| `--force` | Off | Replace an existing output file; requires `--output`; project inputs remain protected |

Inspection never changes authored project inputs; `--output` explicitly writes a
separate SQL export, creating parent directories as needed. Selected columns retain row-affecting joins, filters,
grouping and multiplicity. `--compile false` retains dbt relation templates;
true uses literal source declarations or applicable manifest evidence. Unresolved
names remain templates with warnings. It never evaluates profiles or verifies
warehouse existence. The plan is not a warehouse execution plan.
By default, repeated rewrite reasons are summarized and applied rules are listed
once per model. `--verbose` restores detailed rule, scope and occurrence information;
it does not change the SQL or safety checks.

Copying and saving exclude CLI notices and diagnostics, even with `--verbose`;
comments already in the rendered SQL are preserved. Terminal output and safety
warnings remain visible. Both options can be combined; the file is saved before
copying, so a clipboard failure does not lose the export. Clipboard failures return
a nonzero exit status. Clipboard support uses PowerShell on Windows, `pbcopy` on
macOS, and `wl-copy` (Wayland), `xclip` or `xsel` (X11) on Linux. Headless sessions
should use `--output` instead.

See the [inspection guide](../guides/inspection-and-optimization.md) for SQL
comparisons and the [partial optimization guide](../guides/partial-optimization.md)
for transformation outcomes and static-template boundaries.

## Export

```bash
extra export --format xlsx --select customer_revenue
extra export --format csv --output-dir extra/review-csv --preview
extra export --format json --select customer_revenue orders demo_raw_orders
extra export --view finance --preview
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--format xlsx\|csv\|json` | `xlsx` | Review format; JSON is read-only |
| `--output-dir PATH`, `--path PATH` | `extra/review` | Destination relative to the project root |
| `--view NAME` | `export.default_view`, if set | Named `export.views` override |
| `--expand`, `--no-expand` | Off | Static local macro previews; generated SQL is read-only |

Export writes review outputs only. It may replace the same output filenames but
never prunes unrelated files. Use separate directories for independent reviews.
A view overrides base format/select/exclude/expand settings; explicit flags
override the view. See [review tables and JSON](catalogs.md).

## Import

```bash
extra import extra/review/review.xlsx --preview
extra import extra/review-csv --preview
```

`PATH` is an existing XLSX workbook or complete CSV export directory, including
`_baseline.json`. It is relative to the current directory, not the project root.
JSON cannot be imported. Supported edits patch original dbt files; remove
`--preview` only after reviewing the diff. Keep hidden identities and baselines,
close Excel, and re-export after stale-source conflicts. See the
[round-trip walkthrough](../guides/catalog-round-trip.md) and
[import rules](catalogs.md#import-rules).

## Optimize

```bash
extra optimize --select customer_revenue --format compact --enrich true --preview
extra optimize --select macro_revenue --expand true --preview
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--format pretty\|compact` | `pretty` | SQL and supported leading Jinja `config()` layout |
| `--expand true\|false` | `false` | Replace supported static local macros/templates with SQL |
| `--enrich true\|false` | `false` | Include missing-metadata proposals for the same selection |

Unlike export's paired flags, inspect/optimize Boolean options require a value.
Optimization edits selected authored model SQL, never compiled SQL or upstream
definitions. Expansion preserves `ref()`, `source()` and `config()`; it does not
edit macro definition files. Unsupported expansion skips the model unchanged.

Reports separate structural rewrites, qualification, formatting-only changes,
unchanged models and skips. Applied/blocked/rolled-back rule outcomes and retained
boundaries explain partial work. A blocked rule can leave unrelated safe work
intact. See [optimizer safety](../guides/source-optimizer-safety.md).

## Enrich

```bash
extra enrich --select customer_revenue --preview
```

Fills missing inferred types and unambiguous passthrough descriptions in existing
writable dbt model entries. Reports inferred and unresolved properties; authored
values are not overwritten. See [metadata enrichment](../guides/metadata-enrichment.md).

## Exit status and automation

Successful commands, including previews, return 0. Skipped models, unavailable
analysis and unresolved metadata can still return 0: inspect the coverage/report,
not just the exit status. Reported project, conflict and file errors return 1;
invalid CLI usage returns 2. Human-readable output is not a stable machine
protocol; use version-tested [Python integrations](python-api.md) or read-only
JSON where appropriate.
