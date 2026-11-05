# Migrating from slbt

dbt-extra starts at **0.1.0** in a new private repository with fresh Git history.
The original slbt repository and local checkout are not renamed or modified.
This is a new distribution, not a slbt patch release.

## Renamed interfaces

| Surface | Previous | dbt-extra 0.1.0 |
| --- | --- | --- |
| Repository | `billybillysss/slbt` | `billybillysss/dbt-extra` |
| Distribution | `slbt` | `dbt-extra` |
| Command | `slbt` | `extra` |
| Python imports / module command | `slbt` / `python -m slbt` | `dbt_extra` / `python -m dbt_extra` |
| Optional tool settings | `slbt_project.yaml` | `extra_project.yaml` |
| Project environment variable | `slbt_PROJECT_DIR` (or uppercase on Windows) | `EXTRA_PROJECT_DIR` on every platform |
| Default review directory | `slbt_review` | `extra_review` |
| New property file default | `_slbt_properties.yml` | `_extra_properties.yml` |
| Read-only JSON format | `slbt.dbt-review` | `dbt-extra.dbt-review` |
| Editable review baseline | `slbt.dbt-review-baseline` | `dbt-extra.dbt-review-baseline` |

There are deliberately **no compatibility aliases**. Remove old environment
variables and update scripts, integrations, editor settings and CI explicitly.
Settings schema version and review format version remain **2**; the structure
has not been replaced with a new authoring language. Internal generated SQL
aliases, workbook row IDs and staging-file suffixes also use the `extra` prefix.

## Move an existing native dbt project

1. Commit or back up your authored dbt files and finish outstanding reviews with
   the old version. Keep the old environment available until verification is done.
2. Install this authorized checkout in a **new environment**:

   ```bash
   git clone https://github.com/billybillysss/dbt-extra.git
   cd dbt-extra
   uv sync --locked
   uv run --locked extra --version
   ```

3. Rename a version-2 `slbt_project.yaml` to `extra_project.yaml`. Review explicit
   `export.output_dir` values: a configured old directory stays explicit until
   you change it to `extra_review`. dbt project paths and SQL dialect are unchanged.
   Settings are optional; `extra init path/to/project --preview` shows a new file
   without writing it. Initialization refuses to overwrite existing new settings.
4. Update imports to `dbt_extra` and environment variables to `EXTRA_PROJECT_DIR`.
   Prefer explicit project selection when checking the migration:

   ```bash
   uv run --locked extra --project-dir path/to/project --dialect duckdb validate
   uv run --locked extra --project-dir path/to/project --dialect duckdb optimize --preview
   uv run --locked extra --project-dir path/to/project --dialect duckdb export --format xlsx --preview
   ```

   Replace `duckdb` with the project's actual dialect. Validation is offline,
   not a dbt build or a warehouse execution check.
5. **Export fresh reviews.** Old XLSX/CSV baselines are rejected. Do not edit
   hidden identifiers or relabel a baseline to bypass validation; reapply approved
   changes to a fresh export. Read-only JSON consumers must check the new format.
6. Compare proposed diffs, then run your own dbt parse/build/tests before accepting
   source changes. Read-only and preview operations must leave authored bytes intact.

Existing dbt property files named `_slbt_properties.yml` remain valid native dbt
YAML. Do not duplicate or rename them solely for branding: dbt-extra discovers
authored properties normally. `_extra_properties.yml` is only the default for
new missing-property files. Explicit `metadata.new_properties_file` is respected.

## Earlier compile-to-dbt authoring

The old PyPI `slbt==0.2.0` used the earlier compile-to-dbt authoring workflow.
Renaming its version-1 model specifications is **not** a migration to native dbt.
Keep that installation separate, obtain and verify a native dbt project using
the old workflow, and adopt dbt-extra only after native SQL/YAML are authoritative.
There is no automatic version-1 specification converter in dbt-extra.

## Release and artwork status

The repository stays private during verification. Making it public and publishing
to PyPI need separate approval; neither follows automatically from passing tests.
The initial commit is the first source version. The maintainer-supplied Modular
joint / Lagoon SVG icon is included under dbt-extra asset names, preserving its
geometry and colors. The old slbt wordmark and workflow diagram are not carried
over; the README pairs the approved icon with a text title.
