# CLI reference

```text
extra [--version] [--project-dir PATH] [--dialect DIALECT] [--manifest PATH] COMMAND
```

Project selection is **`--project-dir` > `EXTRA_PROJECT_DIR` > nearest
`dbt_project.yml` upward from the current directory**. Explicit directories must
contain `dbt_project.yml`; optional `extra_project.yaml` is loaded only beside it.
Global options go before the command. dbt-extra never runs dbt or connects to a warehouse.

CLI input paths (`--project-dir`, `--manifest`, `import PATH`) and relative
`EXTRA_PROJECT_DIR` values are relative to the current directory. Configured paths
and export `--output-dir` / `--path` are relative to the project root; absolute
paths stay absolute. See [configuration](configuration.md#relative-paths).

## Commands

| Command | Purpose | Writes by default |
| --- | --- | --- |
| `init` | Add optional version-2 settings at the selected dbt root | New settings only; refuses overwrite |
| `validate` | Check resource structure, Jinja structure, static SQL and reference cycles | No |
| `inspect MODEL` | Explain full/selected-column definition SQL or logical plan | No |
| `export` | Produce XLSX, CSV, or read-only JSON | Review outputs only; no pruning |
| `import PATH` | Apply supported review edits with baseline checks | Original dbt files |
| `optimize` | Conservative authored SQL rewriting | Selected `.sql` files |
| `enrich` | Fill missing types/passthrough descriptions | dbt property YAML |

Every writing command accepts `--preview`: show intended
outputs or source diffs without creating directories, temporary files or outputs.

`init` uses the same discovery as every other command. Run `extra init --preview`
inside a project, or `extra --project-dir PATH init --preview` from outside it.
There is no positional directory argument.

## Select resources

`export`, `optimize`, and `enrich` support repeated `--select/-s` and `--exclude`,
each accepting multiple values. Explicit lists replace, rather than append to,
configuration. Omitted lists leave configuration unchanged.

```bash
extra export --format xlsx --select orders customers
extra export --select 'path:models/gld/**' --exclude macro_revenue
extra export --select 'tag:finance' --view finance
extra optimize --select model.jaffle_shop.customer_revenue --preview
```

Supported selector forms: name/glob, exact resource ID, `name:`, `id:`, `path:`,
`tag:`, `package:`, `resource_type:`. These are dbt-extra's documented subset, not the
complete dbt selector language; graph operators and intersections are unsupported.
Optimization and enrichment operate on SQL models, not source/group metadata.

## Inspect

```bash
extra inspect customer_revenue
extra inspect customer_revenue --columns revenue customer_id
extra inspect customer_revenue --columns revenue --from orders --view plan
extra inspect customer_revenue --optimize false --expand false
extra inspect customer_revenue --compile false
```

`--columns` and `--from` accept multiple/repeated values. Boundaries must be
upstream models. Defaults are full model, upstream/static-local-macro expansion, optimized logical
SQL, physical relation names (`--compile true`), and `--view sql`.
`--compile false` retains dbt relation templates. Compilation resolves literal
source names or applicable manifest relation evidence; unresolved names remain
templates with a coverage warning. It never runs `dbt compile`, evaluates profiles,
or verifies warehouse existence. Use a current manifest for the intended target.
`--view plan` is a logical tree, not a warehouse plan.
`--dialect` can be supplied globally or on SQL-related commands.

## Export and import

```bash
extra export --format xlsx --output-dir extra/review
extra export --format xlsx --expand
extra export --format csv --preview
extra export --format json --select customer_revenue
extra import extra/review/review.xlsx --preview
extra import extra/review/review.xlsx
extra import extra/review --preview
```

`--output-dir` (`--path` alias), `--format xlsx|csv|json`, and `--view NAME`
override export settings. `--expand` / `--no-expand` controls static local macro
previews (off by default). Bounded literal expressions, nested local calls, and
literal-list loops are supported; adapter/database/environment-dependent output
remains unknown. Resolved SQL produces column mappings without extra TEMPLATE rows;
unresolved calls remain TEMPLATE rows with reasons. Generated expressions are read-only;
edit hidden Authored SQL or macro definitions, or re-export without expansion to edit calls.
XLSX is the default. CSV import requires the complete
export directory, including `_baseline.json`. JSON is read-only, not an import
format. See the [review contract](catalogs.md).

## Optimize and enrich

```bash
extra optimize --select customer_revenue --format pretty --preview
extra optimize --select customer_revenue --format compact --enrich true
extra optimize --select macro_revenue --expand true --preview
extra enrich --select customer_revenue --preview
```

`pretty` also formats leading Jinja `config()` calls with one argument per line
and indented dictionaries/lists. `compact` keeps these calls on one line (except
authored multiline strings). Quotes, values, key order, and dynamic expressions
are preserved without evaluating Jinja; other Jinja calls are not reformatted.
Unsupported config syntax is preserved unchanged.

`--expand true|false` controls macro writeback (default: false). False preserves
authored macro calls. True replaces statically resolvable local macros, including
nested calls, literal-list loops, multiple-column output and SQL clauses, with SQL
before optimization. Applying writes that SQL to the original model; `--preview`
only shows the proposed diff. `ref()`, `source()` and `config()` remain authored;
upstream model SQL is not inlined. Unsupported/runtime-dependent macros skip the
whole model unchanged with a reason. Macro definition files are not edited.
Optimization never requires compiled SQL. Enrichment reports inferred and
unresolved properties and never overwrites existing authored values.
See [SQL functions](sql-functions/README.md) for implemented Spark/T-SQL gaps and verified examples
and the distinction between parsing, type inference and safe rewriting.

Offline `validate` is not `dbt parse`, `dbt compile`, `dbt build`, warehouse SQL
validation, or an enforced-contract check. Unsupported analysis is explicitly
reported rather than counted as executed dbt validation.
