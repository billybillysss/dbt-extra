# Integrate with an existing dbt project

Point dbt-extra at your dbt project. Existing paths, SQL and properties stay in place.

```bash
extra --project-dir path/to/project --dialect snowflake validate
extra --project-dir path/to/project --dialect snowflake export --format json --preview
extra --project-dir path/to/project --dialect snowflake inspect your_model --columns your_column
extra --project-dir path/to/project --dialect snowflake optimize --select your_model --preview
```

Use the actual project dialect. Optional artifacts improve identity/config/schema
evidence, but compiled SQL is never reconstructed as authored source. Disagreement
between current files and manifest is diagnostic, not permission to overwrite files.

Begin read-only on a small selection, inspect coverage reasons, and try a
metadata-only import preview. Unsupported templates remain reviewable source,
without pretending their internals are understood. Run dbt checks independently.
Optional settings live beside `dbt_project.yml`. To avoid repeating the directory,
run inside that project or set `EXTRA_PROJECT_DIR` (or the lower-priority
`DBT_PROJECT_DIR`); an explicit `--project-dir` overrides both environment variables.
See [project resolution and migration](../reference/configuration.md#resolution-and-precedence).
No credentials or profile copying is needed.

## What is discovered

Discovery honors dbt's configured `model-paths`, `macro-paths`, `snapshot-paths`
and `seed-paths`, with the usual `models`, `macros`, `snapshots` and `seeds`
defaults. Roots must stay inside the project and must not overlap.

| Resource | Offline coverage |
| --- | --- |
| SQL models (`.sql`) | SQL/column analysis, inspection and guarded source optimization |
| Python models (`.py`) | Source and metadata review; no Python execution or SQL rewriting |
| Sources and property YAML (`.yml`, `.yaml`) | Metadata, declared columns and available relation evidence |
| SQL/YAML snapshots and CSV seeds | Discovery and review; not an evaluation of snapshot history or seed data |
| SQL macros and documented macro entries | Source/documentation review; bounded static expansion where supported |
| Manifest-only or installed-package resources | Supplemental evidence and read-only review |

Property files are read under the configured resource roots. Current authored
files take precedence over stale artifact content. Versioned model metadata and
inherited properties can be read-only; review their reported reasons rather than
assuming every discovered resource is writable.
