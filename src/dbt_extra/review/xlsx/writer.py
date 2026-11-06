"""Serialize the hierarchical review layout and its checked import baseline."""

import io

from openpyxl import Workbook
from openpyxl.styles import Font

from dbt_extra.review.contract import json_text
from dbt_extra.review.xlsx.layout import build_layout
from dbt_extra.review.xlsx.styles import forest_paper_theme, style_legend, write_sheet


def write_workbook(project, tables, baseline, *, expand=False):
    sheets = build_layout(project, tables, expand=expand)
    baseline = {**baseline, "workbook": {"version": 1, "sheets": sheets}}
    book = Workbook()
    book.loaded_theme = forest_paper_theme()
    legend = book.active
    legend.title = "README"
    for row in [
        ["dbt-extra dbt review", "Native dbt SQL/YAML remain authoritative. Sheets follow package and native model/folder paths; no dbt-extra defaults or layer/domain registry."],
        ["Hierarchy", "TABLE > STEP / OUTPUT > COLUMN; SOURCE > TABLE > COLUMN. Collapse outlines to scan tables."],
        ["Editable cells", "Unlocked cells: authored metadata, supported SELECT clauses, Distinct and projection expressions. Context is read-only."],
        ["Structured metadata", 'Config / Meta / Properties: JSON objects. Tests / Constraints: JSON arrays. Example Tests: ["not_null"]. Blank removes the authored field.'],
        ["Example (not imported)", 'COLUMN customer_id: Description = Customer identifier; Data Type = bigint; Tests = ["not_null", "unique"].'],
        ["SQL edits", "Edit supported STEP/OUTPUT clauses (FROM/JOIN/WHERE/GROUP BY/etc.) or column expressions. Keep aliases in Name unchanged. Distinct: true or blank."],
        ["Full source", "Authored SQL columns are hidden to keep the hierarchy compact; unhide to edit full source instead of structured SQL cells. Macro Expression edits only the named macro; documentation writes to Properties File."],
        ["Configuration", 'Edit authored package/folder Config at its original dbt_project.yml Scope, e.g. models.jaffle_shop. Empty scopes are omitted. Preserve + prefixes, e.g. {"+materialized": "view"}. Inherited config is not flattened into authored fields.'],
        ["Paths and templates", "Path is the project-relative folder, e.g. models/slv. Simple references use ref.model / source.group.table; calls use macro.name(arguments). Imports restore dbt Jinja. Complex templates retain their syntax."],
        ["Macro columns", "Known single-column scalar, aggregate and window calls stay COLUMN expressions using macro.name(...). Each call is classified independently; only unresolved or unexpanded multi-column/clause output stays TEMPLATE."],
        ["Package", "Read-only owning dbt project/package, e.g. jaffle_shop. Distinguishes same-named resources in different packages; it is not a folder path."],
        ["CASE template example", "CASE WHEN amount > 0 THEN macro.round_money('amount') ELSE 0 END. Supported scalar calls remain editable column expressions; opaque calls stay TEMPLATE rows."],
        ["Macro expansion", "export --expand derives COLUMN mappings from resolved macro SQL, without extra TEMPLATE rows. Generated expressions/clauses are read-only; edit Authored SQL or the macro definition. Unresolved output stays TEMPLATE with its reason; no column count is guessed."],
        ["Safety", "Keep all rows, sheets and the hidden baseline/identities. No additions, deletions, renames or moves. Stale files, formulas and read-only edits are rejected."],
        ["Limitations", "Opaque Jinja and unsupported query shapes stay visible but cannot be structurally rewritten. Full source receives structural checks, not dbt execution. Run dbt validation independently."],
    ]:
        legend.append(row)
    style_legend(legend)
    for spec in sheets:
        write_sheet(book, spec)
    hidden = book.create_sheet("_baseline")
    raw = json_text(baseline)
    for offset in range(0, len(raw), 30000):
        hidden.append([raw[offset:offset + 30000]])
        hidden.cell(hidden.max_row, 1).data_type = "s"
        hidden.cell(hidden.max_row, 1).font = Font(name="Arial", size=10)
    hidden.sheet_state = "veryHidden"
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()
