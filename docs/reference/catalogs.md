# Review tables and JSON

Direct `extra export` supports `--format xlsx|csv|json`. dbt files remain
authoritative; tables are editable reviews, not another transformation language.

## Hierarchical XLSX

XLSX uses a table-oriented review layout:

- Model sheets follow authored folders, with separate package
  groups. `Path` uses slash-separated project-relative parent
  folders, including the root: `models/staging`, `macros`, `macros/helpers`.
  Source File retains its filesystem path. Long/invalid Excel
  tab names are shortened/sanitized without changing resource identity.
- Rows form **TABLE → STEP / OUTPUT → COLUMN**. STEP rows represent authored CTEs;
  OUTPUT represents the final query. Sources use **SOURCE → TABLE → COLUMN**.
  Macro sheets show one row per named macro, combining SQL with YAML description
  and arguments by macro name (not filename). Seeds and snapshots have separate groups.
- Model headers start with `Type`, `Path`, `Name`, followed by SELECT controls
  through `Expression`, `Data Type`, `Description`, `Config`, `Constraints`,
  `Tests`, `Meta`. Additional columns retain arbitrary `Properties`, exact source
   identity and analysis status/reasons. Version, Layer, Domain, Upstream Columns,
   Effective Config, Snapshot, and custom References columns are not shown;
   underlying metadata is preserved. Official dbt relationship information remains
   in Tests (`relationships`) and Constraints (`foreign_key`).
- `Package` is read-only context identifying the owning dbt project/package, e.g.
   `jaffle_shop`. It distinguishes same-named resources across packages, not folders.
- [Forest + Paper](https://bigexcelenergy.com/excel-dashboard-color-palette/)
  supplies charcoal headers, forest-green summaries, paper STEP rows and a derived
   pale-sage OUTPUT tint. Snapshot TABLE rows use a distinct blue-green summary fill,
   based on dbt's configured snapshot roots rather than a hardcoded folder name.
   Output column rows are pure white. Matching Office theme
  colors are embedded in the workbook. Outlines, indentation, wrapped text, content-aware heights,
  frozen identity columns, filters and repeated print headers aid scanning.
- Green text on light rows / unlocked cells identify supported edits; dark summary
  rows use white text. Config, Meta and
  Properties use JSON objects; Tests and Constraints use JSON arrays. Tests maps
  to the existing `data_tests` or `tests` key (new tests use `data_tests`). Other
  authored fields stay in Properties, rather than being discarded.
- STEP/OUTPUT Expression contains SELECT clauses (FROM/JOIN/WHERE/GROUP BY/etc.).
  Supported clauses, Distinct (`true`, `false`, or blank), and individual explicit
  projection expressions can be edited at their original SQL scope. CTE column
  metadata is read-only; final-output column metadata writes to dbt properties.
  Unsupported shapes and opaque Jinja remain visible without guessed rewrites.
- Full `Authored SQL` columns are hidden by default to keep the main hierarchy
  compact; unhide them for full-source edits. Macro `Expression` edits only its
  named block, preserving other macros and surrounding file content. Description /
  Properties edits go to the original YAML entry shown in `Properties File`.
  Undocumented macros and documentation-only entries remain visible.
- Simple references display as `ref.customer_revenue`, `source.raw.orders`, or
  `macro.round_money('amount')`, including package names when present. Import
  restores valid Jinja, retaining original call spelling where possible.
  Complex/dynamic templates and versioned references retain their original syntax.
- Known single-column macro calls appear in `COLUMN` expressions as `macro.XXX(...)`,
  including scalar, aggregate and window expressions. Calls are classified independently:
  an unresolved call does not turn other known calls into templates.
- Unknown or multi-column macro calls remain editable `TEMPLATE` rows with a reason,
  not guessed columns. `extra export --expand` derives column mappings from resolved
  SQL, including one `COLUMN` per output of multi-column macros, without extra TEMPLATE
  rows for resolved calls. Generated SQL is read-only; edit hidden `Authored SQL`,
  the macro definition, or re-export without expansion to edit the original call.
  Output-column metadata remains editable. Runtime/adapter-dependent macros remain
  TEMPLATE rows even with expansion enabled; lineage across unresolved shapes is not inferred.

`Configuration` exposes nonempty authored `models`, `seeds` and `snapshots` package /
folder scopes in `dbt_project.yml`, using dotted scopes such as `models.jaffle_shop`.
Empty parents are omitted without hiding configured descendants.
Edit each Config JSON object with its original
keys (including `+` prefixes). Changes go back to that exact YAML scope, preserving
child scopes and unrelated settings. Blank clears only direct settings, not child
scopes. Mapping-valued settings require `+` to distinguish them from child scopes.
Effective/inherited model config remains available in the JSON analysis catalog;
it is not shown as an XLSX column or flattened into authored YAML.

### CASE expressions containing templates

Authored SQL can contain a scalar macro within a `CASE WHEN` expression:

```sql
case when amount > 0 then {{ round_money('amount') }} else 0 end
```

For a supported local scalar macro, the column Expression displays editable shorthand:

```sql
CASE WHEN amount > 0 THEN macro.round_money('amount') ELSE 0 END
```

Import restores the Jinja call. With `--expand`, the column instead previews the
generated expression, such as `CASE WHEN amount > 0 THEN ROUND(amount, 2) ELSE 0 END`.
That generated expression is read-only, with no extra TEMPLATE row. Edit `Authored SQL`
or the macro definition, or re-export without expansion to edit the call in its COLUMN row.
Unknown or runtime-dependent calls stay TEMPLATE rows without assuming a scalar
output; editing the call preserves the surrounding authored CASE expression.

Keep the `README` legend, all review sheets, hidden row identities and very-hidden
baseline. Workbooks with flat `resources` / `columns` sheets are also supported
for import.

## Flat CSV tables

CSV uses `resources.csv`, `columns.csv` and the required `_baseline.json`.
All formats retain the same
slash-separated project-relative parent-folder `model_path`, separate name, stable resource ID and exact source
file; XLSX presents these alongside the hierarchy.

| Resource fields | Contract |
| --- | --- |
| `resource_id`, `resource_type`, `package`, `model_path`, `name`, `source_file` | Read-only identity and location |
| `description` | Editable authored description |
| `properties` | Editable JSON mapping of authored resource metadata: tests, constraints, config, etc. |
| `sql` | Editable full authored SQL/Jinja for local SQL models, macro files and SQL snapshots |
| `status`, `reason` | Read-only analysis coverage |

| Column fields | Contract |
| --- | --- |
| Identity/name/location fields | Read-only |
| `expression` | Editable only for supported simple root SELECT projections |
| `description`, `data_type` | Editable authored metadata; blank type may be inferred |
| `properties` | Editable JSON mapping of other authored column metadata |
| `upstream_columns`, `status` | Read-only best-effort value lineage |

Descriptions/types appear once, not duplicated in properties. CSV columns appear
in their own table; source groups expose schema/database settings separately from
their source tables. Arbitrary authored dbt metadata is preserved in Properties.
Macro definitions expose docs/arguments; macro-file rows expose full source.

## Import rules

- Keep the original baseline. Files changed since export cause a conflict for
  affected edits; re-export rather than overwriting concurrent work.
- No resource/column row additions or deletions, renames or path moves in v2.
  Inferred column rows already present at export can gain authored metadata.
- Choose full SQL **or** structured scope/projection edits for a model, not both. Expressions
  cannot inject statements, arbitrary templates, renames, or change a complex
  query's interface. Supported static ref/source/scalar-macro calls are reversible.
  Expanded preview expressions are read-only in CSV as well as XLSX.
- Full opaque-template edits receive Jinja structure validation only. Static
  SQL receives read-only query checks. Neither is a substitute for dbt validation.
- Read-only package/artifact resources and version-inherited properties cannot
  be edited. YAML aliases/merge structures refuse automated metadata rewrites.
- XLSX formula cells are rejected; exported strings beginning `=` remain literal
  text. CSV is raw text: use a spreadsheet's text-import mode, not automatic
  formula interpretation, when opening untrusted descriptions or source code.
  XLSX cells exceeding Excel's length limit
  fail explicitly; use CSV or JSON rather than silently truncating SQL.
- Unchanged files retain original bytes. Changed property documents use
  round-trip YAML preserving comments/quotes and unrelated entries.

Import is preflighted as a whole. Files are staged and replacements attempt
rollback on failure; no crash-safe transaction or concurrency lock is claimed.
Preview reports the same proposed diffs without writing files.

## Read-only JSON

`review.json` has `format: dbt-extra.dbt-review`, `format_version: 2`,
`source_of_truth: dbt`, dialect/artifact metadata, coverage counts, diagnostics and
resources. Each resource includes authored SQL/properties, available config,
dependency resolution, query context and analyzed columns with explicit
status/reasons/provenance. Unknown schema, opaque Jinja and partial value lineage
remain explicit. JSON is analysis context, not an editable import format or a
substitute for join/filter context when explaining business behavior.
