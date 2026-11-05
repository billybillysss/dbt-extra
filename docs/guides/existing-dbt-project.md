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
run inside that project or set `EXTRA_PROJECT_DIR`; an explicit `--project-dir`
overrides both. See [project resolution and migration](../reference/configuration.md#resolution-and-precedence).
No credentials or profile copying is needed.
