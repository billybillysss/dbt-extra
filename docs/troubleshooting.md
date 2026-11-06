# Troubleshooting

## No dbt project found

Run from the right directory or use
`uv run extra --project-dir examples/jaffle_shop validate`. The global option comes
before the command. Project selection is `--project-dir` > `EXTRA_PROJECT_DIR` >
`DBT_PROJECT_DIR` > nearest ancestor containing `dbt_project.yml`.
The selected directory must contain `dbt_project.yml`; invalid selections do not
fall back to lower-priority sources. Tool settings are
optional and loaded only beside it. `extra --project-dir DIRECTORY init` adds
settings to that root; `init` has no positional directory argument.

## `uv sync --locked` fails

Check Python 3.11+, network access and the actual dependency-resolution error.
Do not bypass the lock silently in CI. After an intentional dependency/metadata
change, maintainers run `uv lock` and review the diff. An offline runtime environment
can use `--no-dev`, but cannot run the adapter-dependent demo/tests without their
dependencies.

## Invalid settings or unknown field

Use version-2 optional settings. Model/macro/snapshot paths belong in
`dbt_project.yml`. Unknown settings and duplicate keys are errors.
Use `optimization.expand: false` to preserve macro calls (the default).
For legacy `dbt.project_dir`, move `extra_project.yaml` beside the intended
`dbt_project.yml`, remove that setting, and select the dbt root directly.
See [configuration](reference/configuration.md).

## Inspection cannot resolve a query

Check the dialect, explicit columns, relation aliases and loaded upstream definitions.
Opaque macros/dynamic templates cannot expand offline. Ambiguous columns, cycles and
unsafe relation modifiers report errors rather than using warehouse guesses.
Use `--compile false` to retain dbt ref/source templates; the default resolves
available physical names offline. dbt-extra never executes the output.
Inspection explains definitions, not stored data. A logical plan is not warehouse
EXPLAIN. Missing schemas can prevent SELECT * expansion.

## Optimization succeeds but a model is unchanged

It may already be normalized or depend on a runtime macro. Read the coverage
messages and stderr for skips.
Other eligible models can still be optimized. A successful exit does not mean
every model changed, every metadata property resolved, or a speedup was measured.

## Excel import/export fails

Close Excel first to release file locks. Use plain-text SQL/JSON, not formulas or
error cells. Preserve identities, rows, directory paths and read-only fields.
Keep the hidden baseline or CSV `_baseline.json` sidecar. Re-export when sources
changed; do not bypass conflicts. Import CSV as a directory and never import JSON.
See the [round-trip guide](guides/catalog-round-trip.md).

## Review files remain

Exports never prune unrelated files. Use a dedicated review directory; changing
formats does not delete old formats. Import wanted workbook edits before replacing
the workbook.

## dbt cannot find models or macros

Check resource paths in `dbt_project.yml` and look for name collisions.
extra does not create profiles, download packages or execute dbt. Use the
[integration guide](guides/existing-dbt-project.md). The native demo's project/profile
directory is `examples/jaffle_shop`.

## A command failed while writing

Stop other writers. Review Git diffs and native inputs, restore only changes
you deliberately choose from version control/backups, revalidate, then regenerate
outputs in a clean directory. Do not assume all mutations rolled back after a
filesystem error or process interruption. See the
[write-boundary checklist](guides/production-workflow.md#file-mutation-and-deployment).

For an issue, include `extra --version`, Python/OS, the command, the error and a
minimal redacted reproduction. Do not attach credentials, private catalog data
or live database files. Follow [security reporting](../SECURITY.md) for vulnerabilities.
