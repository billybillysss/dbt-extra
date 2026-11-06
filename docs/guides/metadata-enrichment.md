# Fill missing metadata

`enrich` proposes missing column types and descriptions in existing dbt model
property entries. It never overwrites nonempty authored values or creates a
properties file. Type inference uses SQL and available schema evidence;
descriptions pass through only unambiguous bare-column projections or renames.
Transformed expressions do not inherit an upstream description.

## Preview a proposal

From `examples/jaffle_shop`, run:

```bash
uv run extra enrich --select customer_revenue --preview
```

The preview reports `4 missing properties inferred; 2 unresolved`: three types
and the passthrough description of `customer_id`. It does not invent descriptions
for transformed `revenue` or `order_count`. Preview writes nothing.

## YAML proposal

These excerpts show the `customer_revenue` entry in `models/schema.yml`, before
and after accepting the proposal. Other resource entries are omitted.

Before:

```yaml
version: 2
models:
  - name: customer_revenue
    description: Completed-order revenue per customer, not a governed metric definition.
    config:
      meta:
        owner: finance
    columns:
      - name: customer_id
      - name: revenue
      - name: order_count
```

After:

```yaml
version: 2
models:
  - name: customer_revenue
    description: Completed-order revenue per customer, not a governed metric definition.
    config:
      meta:
        owner: finance
    columns:
      - name: customer_id
        data_type: BIGINT
        description: Customer identifier.
      - name: revenue
        data_type: DECIMAL(38, 2)
      - name: order_count
        data_type: BIGINT
```

Remove `--preview` to apply on a review branch or disposable project copy.
Inspect the Git diff and run dbt checks before accepting the change.

## Selection and inference limits

- `--select/-s` and `--exclude` use the shared [selectors](../reference/cli.md#select-resources).
  Defaults come from the `metadata` settings section. Only local SQL models with
  writable, nonversioned property entries are eligible.
- Missing YAML entries and read-only/versioned metadata are skipped with a reason.
  Add a model entry in dbt first and retry. Inferred columns can be added inside
  an existing entry.
- Missing schema, unsupported functions or opaque Jinja can leave individual
  properties unresolved. A successful command does not mean every property was
  inferred. See [SQL-function type policies](../reference/sql-functions/README.md)
  for dialect-specific coverage.
- Existing semantic models, entities, dimensions and metrics are preserved, not
  inferred or converted. Enrichment does not require the dbt Semantic Layer.

To combine SQL cleanup and metadata proposals, run
`extra optimize --select customer_revenue --enrich true --preview`.
That command uses `optimization` selection settings for both proposals; it does
not merge in the separate `metadata` selection. Both changes remain subject to
source-snapshot conflict checks.
