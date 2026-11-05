# CLI reference

```text
extra [--version] [--project-dir PATH] [--dialect DIALECT] [--manifest PATH] COMMAND
```

`--project-dir` and the exact `EXTRA_PROJECT_DIR` environment variable select the
project/settings directory. Settings and dbt projects without settings are
also discovered by searching upward. dbt-extra never runs
dbt or connects to a warehouse.

## Commands

| Command | Purpose | Writes by default |
| --- | --- | --- |
| `init [DIRECTORY]` | Add optional version-2 settings to an existing dbt project | New settings only; refuses overwrite |
| `validate` | Check resource structure, Jinja structure, static SQL and reference cycles | No |
| `inspect MODEL` | Explain full/selected-column definition SQL or logical plan | No |
| `export` | Produce XLSX, CSV, or read-only JSON | Review outputs only; no pruning |
| `import PATH` | Apply supported review edits with baseline checks | Original dbt files |
| `optimize` | Conservative authored SQL rewriting | Selected `.sql` files |
| `enrich` | Fill missing types/passthrough descriptions | dbt property YAML |

Every writing command accepts `--preview` (`--dry-run` alias): show intended
outputs or source diffs without creating directories, temporary files or outputs.

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
extra export --format xlsx --output-dir extra_review
extra export --format xlsx --expand
extra export --format csv --preview
extra export --format json --select customer_revenue
extra import extra_review/review.xlsx --preview
extra import extra_review/review.xlsx
extra import extra_review --preview
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
extra enrich --select customer_revenue --preview
```

`--preserve-macro true` is the native safety invariant. Setting it false is an
error: compiling/expanding a macro is not a reversible authored-source rewrite.
Optimization never requires compiled SQL. Enrichment reports inferred and
unresolved properties and never overwrites existing authored values.

Offline `validate` is not `dbt parse`, `dbt compile`, `dbt build`, warehouse SQL
validation, or an enforced-contract check. Unsupported analysis is explicitly
reported rather than counted as executed dbt validation.
