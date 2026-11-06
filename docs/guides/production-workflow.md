# Production adoption checklist

This is an adoption checklist, not a production-readiness certification. dbt-extra is
currently 0.2.2. Validate its behavior on your data, dialect, adapter and deployment
environment before using it for a production workload.

## Reproducible review

- Pin the dbt-extra version and Python/runtime dependencies. Keep `uv.lock` when
  working from this checkout; use `uv sync --locked` in CI.
- Version native dbt SQL, properties, macros, snapshots and tool settings together.
- Pin dbt, adapter and packages independently in your integrating project.
- Export reviews outside dbt inputs; import wanted edits before replacing a workbook.
- Run one writer per project/output root; there is no concurrency lock.

## Review gate

Prepare a bounded review context: the requested change and acceptance criteria,
relevant native SQL/properties/macros, and any [read-only JSON analysis](../reference/catalogs.md#read-only-json).
Include upstream definitions explicitly where needed; selection does not include
them automatically. Keep coverage reasons and unknowns visible rather than
inventing missing sources, columns, types or business definitions.

1. Review proposed changes and business assumptions, regardless of who or what
   authored them. Prefer minimal SQL/YAML diffs; preserve config/ref/source Jinja,
   opaque macros, output names/order, tests and constraints unless the request
   explicitly changes them.
2. Run offline `validate`, inspect affected logic and use `--preview` for proposed
   `optimize`, `enrich` or `import` source diffs without writes.
3. Apply approved changes on a branch and inspect the Git diff.
4. Independently run dbt parse/build/tests with
   a controlled profile. Test joins, grain, nulls, monetary units and edge cases.
5. Review contracts/constraint support and snapshot behavior on the real adapter.
6. Refresh JSON, editable review tables and dbt docs as required, after importing
   wanted workbook edits. Record build versions, logs and test results.

For the bundled demo, start with read-only checks and a source preview:

```sh
uv run extra --project-dir examples/jaffle_shop validate
uv run extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --view plan --compile false
uv run extra --project-dir examples/jaffle_shop optimize -s customer_revenue --preview
```

Review aggregation grain, join cardinality, filters, NULL behavior, monetary units
and dependency coverage. If runtime macros block offline inspection, use controlled
dbt compilation and adapter-specific tests; a successful validation is not business
rule verification or authorization to execute/write. After approving the source
diff, run dbt acceptance tests with your own controlled profile. Add result
assertions for the requested change, not just compilation checks, and record the
request, assumptions, reviewed diff and results in the pull request. Logical
optimization does not guarantee faster warehouse execution.

The [native demo](../../examples/jaffle_shop/README.md) exercises one local DuckDB workflow,
not every warehouse. SQLGlot dialect availability is not an adapter support matrix.

## File mutation and deployment

| Operation | Existing protection | Remaining boundary |
| --- | --- | --- |
| Import/optimization/enrichment | Check supported proposals and source baselines; stage writes; attempt rollback on replacement failure. | Not an atomic multi-file transaction. Rollback can fail; crashes may leave partial state. Opaque templates are structure-checked only. |
| Export and initialization | Validate paths, stage writes and attempt rollback. Initialization refuses existing settings; exports never prune. | Not crash-safe or a file-locking mechanism. |
| Paths | Reject unsafe overlap/traversal, symlinks and supported junction cases. | Not a sandbox or protection against all filesystem races. |

Keep Git history/backups for dbt inputs. Use your deployment platform's release
mechanism after dbt acceptance tests. After interruption, inspect source files,
revalidate and re-export reviews; do not assume automatic recovery.

## Security and operations

- Do not store credentials in definitions or generated catalogs. Review metadata
  before sharing with external tools or services; follow the
  [JSON sharing precautions](../reference/catalogs.md#sharing-and-integrations).
- Do not run untrusted dbt macros/projects with production credentials. dbt-extra's
  offline processing does not make later dbt execution safe.
- Keep generated outputs under controlled paths and use least-privilege database
  roles for execution.
- Treat runtime macro skips and unresolved enrichment properties as review items,
  even if a command exits successfully.
- On upgrades, compare generated SQL/JSON and result tests before rollout.

See [security](../../SECURITY.md), [compatibility](../compatibility.md) and
[distribution checks](../development/testing.md#distribution-checks).
