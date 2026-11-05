"""Hierarchical XLSX layout, authored scope bindings, and import boundaries."""

from xml.etree import ElementTree as ET
import json

from openpyxl import load_workbook
import pytest

from dbt_extra.review import export_review, import_review
from dbt_extra.review.import_ import read_review
from dbt_extra.review.export import baseline_for, tables_for
from dbt_extra.analysis import catalog
from dbt_extra.review.workbook import MODEL_HEADERS, workbook
from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import load_yaml
from tests.helpers import project, put, snapshot


def export(root, **kwargs):
    export_review(project(root), **kwargs)
    return root / "extra_review/review.xlsx"


def edit(path, sheet, kind, name, **values):
    book = load_workbook(path)
    tab = book[sheet]
    headers = [c.value for c in tab[1]]
    for row in tab.iter_rows(min_row=2):
        item = dict(zip(headers, [c.value for c in row]))
        if item.get("Name") == name and (kind is None or item.get("Type") == kind):
            for header, value in values.items():
                row[headers.index(header)].value = value
            break
    else:
        raise AssertionError(f"Missing {sheet}/{kind}/{name}")
    book.save(path)
    book.close()


def config_edit(path, scope, value):
    book = load_workbook(path)
    tab = book["Configuration"]
    for row in tab.iter_rows(min_row=2):
        if row[0].value == scope:
            row[1].value = value
            break
    else:
        raise AssertionError(scope)
    book.save(path)
    book.close()


def test_hierarchy_layout_and_forest_paper_theme(native):
    path = export(native)
    book = load_workbook(path)
    assert book.sheetnames == ["README", "gld", "slv", "Sources", "Configuration", "_baseline"]
    tab = book["gld"]
    assert [c.value for c in tab[1]][:len(MODEL_HEADERS)] == MODEL_HEADERS
    assert MODEL_HEADERS[:3] == ["Type", "Path", "Name"]
    assert not {"Version", "Layer", "Domain", "Upstream Columns", "Model Path",
                "Effective Config", "Snapshot", "References"} & {c.value for c in tab[1]}
    assert [tab.cell(i, 1).value for i in range(2, tab.max_row + 1)] == ["TABLE", "STEP", "COLUMN", "COLUMN", "OUTPUT", "COLUMN", "COLUMN"]
    assert [tab.row_dimensions[i].outlineLevel for i in range(2, 9)] == [0, 1, 2, 2, 1, 2, 2]
    assert all(24 <= tab.row_dimensions[i].height <= 150 for i in range(2, 9))
    assert tab.row_dimensions[3].height == 24
    assert tab["A7"].fill.fgColor.rgb == "00FFFFFF"
    assert tab["A4"].fill.fgColor.rgb == "00FFFFFF"
    assert tab["A6"].fill.fgColor.rgb == "00EAF2ED"
    assert tab["A3"].fill.fgColor.rgb == "00F7F8F5"
    assert tab["A2"].fill.fgColor.rgb == "002F7D4F"
    assert tab["A1"].fill.fgColor.rgb == "001F2723"
    headers = [c.value for c in tab[1]]
    assert tab.cell(2, headers.index("Description") + 1).font.color.rgb == "00FFFFFF"
    assert tab.cell(7, headers.index("Expression") + 1).font.color.rgb == "002F7D4F"
    assert tab.cell(7, headers.index("Name") + 1).font.color.rgb == "001F2723"
    assert tab.cell(2, headers.index("Path") + 1).font.color.rgb == "00FFFFFF"
    assert tab["B2"].value == "models/gld"
    assert tab.cell(7, headers.index("Status") + 1).font.color.rgb == "0065726A"
    theme = ET.fromstring(book.loaded_theme)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    scheme = theme.find("a:themeElements/a:clrScheme", ns)
    assert theme.attrib["name"] == scheme.attrib["name"] == "Forest + Paper"
    assert {c.tag.rsplit("}", 1)[1]: c[0].attrib["val"] for c in scheme} == {
        "dk1": "1F2723", "lt1": "FFFFFF", "dk2": "2B5F75", "lt2": "F7F8F5",
        "accent1": "2F7D4F", "accent2": "2B5F75", "accent3": "B56727", "accent4": "6B3FA0",
        "accent5": "007C78", "accent6": "B6424E", "hlink": "2F7D4F", "folHlink": "65726A",
    }
    assert not any("Forest + Paper" in str(row[1].value) for row in book["README"])
    assert not any(row[0].value == "Theme" for row in book["README"])
    assert tab.cell(7, headers.index("Expression") + 1).protection.locked is False
    assert tab.cell(7, headers.index("Name") + 1).protection.locked is True
    assert tab.freeze_panes == "D2"
    assert not tab.sheet_view.showGridLines
    assert not tab.sheet_properties.outlinePr.summaryBelow
    assert tab.page_setup.orientation == "landscape"
    assert tab.page_setup.fitToWidth == 1 and tab.page_setup.fitToHeight == 0
    assert tab.print_title_rows == "$1:$1"
    assert tab.column_dimensions[tab.cell(1, tab.max_column).column_letter].hidden
    assert book["_baseline"].sheet_state == "veryHidden"
    assert all(c.font.name == "Arial" and c.data_type not in {"f", "e"} for s in book for row in s for c in row if c.value)
    sources = book["Sources"]
    assert [sources.cell(i, 1).value for i in range(2, 6)] == ["SOURCE", "TABLE", "COLUMN", "COLUMN"]
    assert [sources.row_dimensions[i].outlineLevel for i in range(2, 6)] == [0, 1, 2, 2]
    book.close()


def test_scoped_sql_metadata_and_config_roundtrip(native):
    with (native / "dbt_project.yml").open("a") as stream:
        stream.write("    # Keep folder config\n    gld:\n      +materialized: table # original scope\n")
    path = export(native)
    edit(path, "gld", "STEP", "base", Expression="FROM {{ ref('orders') }} WHERE amount > 2", Distinct="true")
    # The first id is in base, not OUTPUT: address the visible STEP column.
    edit(path, "gld", "COLUMN", "id", Expression="id + 0")
    edit(path, "gld", "OUTPUT", "OUTPUT", Expression="FROM base WHERE amount > 3 ORDER BY id")
    edit(path, "gld", "COLUMN", "revenue", Expression="amount * 2", Description="Net revenue", Tests='["not_null"]')
    edit(path, "Sources", "SOURCE", "raw", Database="new_landing")
    edit(path, "slv", "TABLE", "orders", Description="Reviewed orders", Meta='{"owner": "ops"}')
    config_edit(path, "models.shop.gld", '{"+materialized": "view", "+tags": ["finance"]}')
    before = snapshot(native)
    changes = import_review(project(native), path)
    assert changes.apply(preview=True)
    assert snapshot(native) == before
    changes.apply()
    sql = (native / "models/gld/revenue.sql").read_text()
    assert "{{ config(materialized='table') }}" in sql and "{{ ref('orders') }}" in sql
    assert "SELECT DISTINCT" in sql and 'id + 0 AS "id"' in sql
    assert "amount > 2" in sql and "amount > 3" in sql and "amount * 2 AS revenue" in sql
    props = load_yaml(native / "models/schema.yml")
    assert props["sources"][0]["database"] == "new_landing"
    assert props["models"][0]["description"] == "Reviewed orders"
    assert props["models"][0]["meta"] == {"owner": "ops"}
    assert props["models"][1]["columns"][1]["data_tests"] == ["not_null"]
    authored = load_yaml(native / "dbt_project.yml")
    assert authored["models"]["shop"]["+tags"] == ["review"]
    assert authored["models"]["shop"]["gld"]["+materialized"] == "view"
    assert "# Keep folder config" in (native / "dbt_project.yml").read_text()
    assert "# original scope" in (native / "dbt_project.yml").read_text()
    # An effective inline config override is not flattened into the scope.
    assert project(native).find("revenue").config["materialized"] == "table"


@pytest.mark.parametrize("header,value", [("Path", "other"), ("Resource ID", "invented"), ("Package", "invented"), ("Name", "renamed")])
def test_readonly_cells_rejected(native, header, value):
    path = export(native)
    edit(path, "gld", "TABLE", "revenue", **{header: value})
    before = snapshot(native)
    with pytest.raises(SpecError, match="Read-only"):
        import_review(project(native), path)
    assert snapshot(native) == before


@pytest.mark.parametrize("action", ["delete", "duplicate", "identity", "sheet", "header", "number"])
def test_structural_changes_rejected(native, action):
    path = export(native)
    book = load_workbook(path)
    tab = book["gld"]
    if action == "delete":
        tab.delete_rows(3)
    elif action == "duplicate":
        tab.append([c.value for c in tab[3]])
    elif action == "identity":
        tab.cell(3, tab.max_column).value = "unknown"
    elif action == "sheet":
        del book["gld"]
    elif action == "header":
        tab["A1"] = "Kind"
    else:
        tab.cell(2, [c.value for c in tab[1]].index("Name") + 1).value = 123
    book.save(path)
    book.close()
    with pytest.raises((SpecError, ValueError)):
        import_review(project(native), path)


@pytest.mark.parametrize("value", ["FROM base; DELETE FROM base", "FROM base UNION SELECT 1", ", 2 FROM base", "FROM {{ ref(var('name')) }}"])
def test_unsafe_scope_edits_rejected(native, value):
    path = export(native)
    edit(path, "gld", "OUTPUT", "OUTPUT", Expression=value)
    before = snapshot(native)
    with pytest.raises(SpecError):
        import_review(project(native), path)
    assert snapshot(native) == before


def test_full_sql_and_structured_scope_conflict(native):
    path = export(native)
    edit(path, "gld", "TABLE", "revenue", **{"Authored SQL": "select 1 as id, 2 as revenue"})
    edit(path, "gld", "STEP", "base", Expression="FROM {{ ref('orders') }} WHERE id > 1")
    with pytest.raises(SpecError, match="SQL or expressions"):
        import_review(project(native), path)


def test_config_conflicts_and_scope_boundaries(native):
    path = export(native)
    config_edit(path, "models.shop", '{"gld": {"+materialized": "view"}}')
    with pytest.raises(SpecError, match="prefix"):
        import_review(project(native), path)
    config_edit(path, "models.shop", '{"+tags": ["reviewed"]}')
    with (native / "dbt_project.yml").open("a") as stream:
        stream.write("# Concurrent edit\n")
    with pytest.raises(SpecError, match="changed since export"):
        import_review(project(native), path)


def test_flat_xlsx_compatibility(native):
    p = project(native)
    tables = tables_for(catalog(p, p.select()))
    baseline = baseline_for(p, tables)
    path = put(native, "old.xlsx", "")
    path.write_bytes(workbook(tables, baseline))
    assert import_review(p, path).apply() == []
    book = load_workbook(path)
    tab = book["resources"]
    for row in tab.iter_rows(min_row=2):
        if row[0].value == "model.shop.revenue":
            row[6].value = "Reviewed description"
    book.save(path)
    book.close()
    import_review(p, path).apply()
    assert load_yaml(native / "models/schema.yml")["models"][1]["description"] == "Reviewed description"


def test_opaque_source_and_macro_source_remain_editable(native):
    put(native, "models/dynamic.sql", "select {{ opaque_macro('amount') }} as amount")
    put(native, "macros/helpers/value.sql", "{% macro value() %}1{% endmacro %}")
    path = export(native)
    edit(path, "Models", "TABLE", "dynamic", **{"Authored SQL": "select {{ opaque_macro('price') }} as amount"})
    edit(path, "Macros · helpers", None, "value", Expression="{% macro value() %}2{% endmacro %}")
    import_review(project(native), path).apply()
    assert "opaque_macro('price')" in (native / "models/dynamic.sql").read_text()
    assert "%}2{%" in (native / "macros/helpers/value.sql").read_text()


def test_macro_definitions_join_source_and_roundtrip(native):
    put(native, "macros/helpers/value.sql", "{% macro value() %}1{% endmacro %}")
    put(native, "macros/helpers/schema.yml", "version: 2\nmacros:\n  - name: value\n    description: Macro documentation\n")
    path = export(native)
    book = load_workbook(path)
    assert [s for s in book.sheetnames if s.startswith("Macros")] == ["Macros · helpers"]
    tab = book["Macros · helpers"]
    assert tab.max_row == 2
    assert tab["A2"].value == "macros/helpers"
    assert tab["C2"].value == "{% macro value() %}1{% endmacro %}"
    assert tab["D2"].value == "Macro documentation"
    assert tab["F2"].value == "macros/helpers/schema.yml"
    book.close()
    assert import_review(project(native), path).apply() == []
    edit(path, "Macros · helpers", None, "value", Expression="{% macro value() %}2{% endmacro %}",
         Description="Reviewed macro", Properties='{"arguments": [{"name": "value", "type": "string"}]}')
    import_review(project(native), path).apply()
    assert (native / "macros/helpers/value.sql").read_text() == "{% macro value() %}2{% endmacro %}"
    props = load_yaml(native / "macros/helpers/schema.yml")["macros"][0]
    assert props["description"] == "Reviewed macro"
    assert props["arguments"] == [{"name": "value", "type": "string"}]


def test_sheet_names_multiple_roots_selection_and_literal_strings(native):
    put(native, "dbt_project.yml", "name: shop\nmodel-paths: [models, reporting]\n")
    a = "finance_" + "a" * 35
    b = "finance_" + "a" * 34 + "b"
    put(native, f"reporting/{a}/alpha.sql", "select 1 as id")
    put(native, f"reporting/{b}/beta.sql", "select 2 as id")
    path = export(native, select=["alpha", "beta"])
    tables, baseline = read_review(path)
    assert {r["name"] for r in tables["resources"]} == {"alpha", "beta"}
    assert {r["model_path"] for r in tables["resources"]} == {f"reporting/{a}", f"reporting/{b}"}
    book = load_workbook(path)
    assert len(set(s.casefold() for s in book.sheetnames)) == len(book.sheetnames)
    assert all(len(s) <= 31 for s in book.sheetnames)
    book.close()
    assert import_review(project(native), path).apply() == []
    # A string starting '=' is serialized as text, never as an Excel formula.
    props = (native / "models/schema.yml").read_text().replace("'All valid orders'", "'=literal description'")
    put(native, "models/schema.yml", props)
    path = export(native)
    book = load_workbook(path)
    tab = book["models · slv"]
    cell = tab.cell(2, [c.value for c in tab[1]].index("Description") + 1)
    assert cell.value == "=literal description" and cell.data_type == "s"
    book.close()


def test_multiple_macros_match_names_and_preserve_surrounding_source(native):
    code = ("-- Keep header\n{# {% macro fake() %}ignored{% endmacro %} #}\n"
            "{% macro first(value) %}{{ value }} * 2{% endmacro %}\n"
            "-- Keep between\n{% macro second(value) %}{{ value }} + 1{% endmacro %}\n"
            "-- Keep footer\n")
    put(native, "macros/helpers/math.sql", code)
    put(native, "macros/schema.yml", "version: 2\nmacros:\n  - name: first\n    description: First docs\n  - name: second\n    description: Second docs\n  - name: docs_only\n    description: No SQL\n")
    path = export(native)
    book = load_workbook(path)
    tab = book["Macros · helpers"]
    assert [tab.cell(i, 2).value for i in range(2, tab.max_row + 1)] == ["first", "second"]
    assert [tab.cell(i, 4).value for i in range(2, tab.max_row + 1)] == ["First docs", "Second docs"]
    assert book["Macros"]["B2"].value == "docs_only"
    book.close()
    assert import_review(project(native), path).apply() == []
    first = "{% macro first(value) %}{{ value }} * 20{% endmacro %}"
    second = "{% macro second(value) %}{{ value }} + 10{% endmacro %}"
    edit(path, "Macros · helpers", None, "first", Expression=first, Description="Reviewed first")
    edit(path, "Macros · helpers", None, "second", Expression=second, Description="Reviewed second")
    import_review(project(native), path).apply()
    assert (native / "macros/helpers/math.sql").read_text() == code.replace("* 2", "* 20").replace("+ 1", "+ 10")
    props = load_yaml(native / "macros/schema.yml")["macros"]
    assert [p["description"] for p in props] == ["Reviewed first", "Reviewed second", "No SQL"]


@pytest.mark.parametrize("expression", ["{% macro renamed() %}2{% endmacro %}",
                                        "{% macro value() %}2{% endmacro %}{% macro extra() %}3{% endmacro %}",
                                        "select 1; {% macro value() %}2{% endmacro %}"])
def test_macro_edits_cannot_rename_or_add_blocks(native, expression):
    put(native, "macros/value.sql", "{% macro value() %}1{% endmacro %}")
    path = export(native)
    edit(path, "Macros", None, "value", Expression=expression)
    before = snapshot(native)
    with pytest.raises(SpecError, match="original named macro"):
        import_review(project(native), path)
    assert snapshot(native) == before


@pytest.mark.parametrize("changed_file,header,value", [
    ("macros/value.sql", "Description", "Reviewed docs"),
    ("macros/schema.yml", "Expression", "{% macro value() %}2{% endmacro %}"),
])
def test_combined_macro_edits_watch_both_source_files(native, changed_file, header, value):
    put(native, "macros/value.sql", "{% macro value() %}1{% endmacro %}")
    put(native, "macros/schema.yml", "version: 2\nmacros:\n  - name: value\n    description: Original docs\n")
    path = export(native)
    edit(path, "Macros", None, "value", **{header: value})
    with (native / changed_file).open("a") as stream:
        stream.write("\n# Concurrent edit\n")
    before = snapshot(native)
    with pytest.raises(SpecError, match="changed since export"):
        import_review(project(native), path)
    assert snapshot(native) == before


def test_undocumented_macros_and_non_macro_files_remain_visible(native):
    put(native, "macros/math.sql", "{% macro first() %}1{% endmacro %}\n{% macro second() %}2{% endmacro %}\n")
    put(native, "macros/custom.sql", "{% test positive(model, column_name) %}select 1{% endtest %}")
    path = export(native)
    book = load_workbook(path)
    tab = book["Macros"]
    rows = {tab.cell(i, 2).value: i for i in range(2, tab.max_row + 1)}
    assert set(rows) == {"first", "second", "custom"}
    assert all(tab.cell(i, 1).value == "macros" for i in rows.values())
    assert tab.cell(rows["first"], 4).protection.locked
    assert not tab.cell(rows["first"], 3).protection.locked
    book.close()
    assert import_review(project(native), path).apply() == []


def test_config_omits_empty_parents_and_keeps_nonempty_children(native):
    put(native, "dbt_project.yml", "name: shop\nmodels:\n  shop:\n    +materialized: view\n    empty: {}\n    staging:\n      nested:\n        +tags: [staged]\nseeds: {}\nsnapshots: {}\n")
    path = export(native)
    book = load_workbook(path)
    tab = book["Configuration"]
    assert [tab.cell(i, 1).value for i in range(2, tab.max_row + 1)] == ["models.shop", "models.shop.staging.nested"]
    book.close()
    assert import_review(project(native), path).apply() == []
    config_edit(path, "models.shop.staging.nested", '{"+tags": ["reviewed"]}')
    import_review(project(native), path).apply()
    assert load_yaml(native / "dbt_project.yml")["models"]["shop"]["staging"]["nested"] == {"+tags": ["reviewed"]}


def test_source_table_selection_keeps_readonly_source_summary(native):
    path = export(native, select=["source.shop.raw.orders"])
    book = load_workbook(path)
    tab = book["Sources"]
    assert [tab.cell(i, 1).value for i in range(2, 6)] == ["SOURCE", "TABLE", "COLUMN", "COLUMN"]
    assert tab["K2"].protection.locked
    assert not tab["K3"].protection.locked
    book.close()
    assert import_review(project(native), path).apply() == []
    edit(path, "Sources", "TABLE", "orders", Description="Selected table")
    import_review(project(native), path).apply()
    assert load_yaml(native / "models/schema.yml")["sources"][0]["tables"][0]["description"] == "Selected table"


def test_config_clear_preserves_child_scopes_and_prefixless_settings(native):
    put(native, "dbt_project.yml", "name: shop\nmodels:\n  shop:\n    materialized: view\n    slv:\n      +tags: [staged]\n")
    assert project(native).find("orders").inherited_config["tags"] == ["staged"]
    assert project(native).find("orders").inherited_config["materialized"] == "view"
    path = export(native)
    config_edit(path, "models.shop", "")
    config_edit(path, "models.shop.slv", '{"+tags": ["staged"], "+meta": {"owner": "ops"}}')
    import_review(project(native), path).apply()
    tree = load_yaml(native / "dbt_project.yml")
    assert tree["models"]["shop"] == {"slv": {"+tags": ["staged"], "+meta": {"owner": "ops"}}}


def test_config_semantic_noop_preserves_original_bytes(native):
    path = export(native)
    before = (native / "dbt_project.yml").read_bytes()
    config_edit(path, "models.shop", '{"+tags": ["review"]}')
    assert import_review(project(native), path).apply() == []
    assert (native / "dbt_project.yml").read_bytes() == before


def test_config_alias_rewrite_rejected(native):
    put(native, "dbt_project.yml", "name: shop\nmodels:\n  shop: &model_scope\n    +tags: [review]\n")
    path = export(native)
    config_edit(path, "models.shop", '{"+tags": ["changed"]}')
    with pytest.raises(SpecError, match="aliases, anchors"):
        import_review(project(native), path)


def test_wrapping_height_cap_and_cell_limit(native):
    put(native, "models/schema.yml", 'version: 2\nmodels:\n  - name: orders\n    description: "' + "long description " * 1000 + '"\n')
    path = export(native)
    book = load_workbook(path)
    assert book["slv"].row_dimensions[2].height == 150
    tab = book["slv"]
    assert tab.cell(2, [c.value for c in tab[1]].index("Description") + 1).alignment.wrap_text
    book.close()
    put(native, "models/schema.yml", 'version: 2\nmodels:\n  - name: orders\n    description: "' + "x" * 32768 + '"\n')
    with pytest.raises(SpecError, match="cell limit"):
        export(native)


def test_nested_cte_identity_is_scope_local(native):
    put(native, "models/nested.sql", """with base as (select 1 as id),
    other as (with base as (select 2 as id) select id from base)
    select base.id, other.id as other_id from base cross join other""")
    path = export(native)
    book = load_workbook(path)
    tab = book["Models"]
    headers = [c.value for c in tab[1]]
    base_columns = []
    for number in range(2, tab.max_row + 1):
        if tab.cell(number, 1).value == "STEP" and tab.cell(number, headers.index("Name") + 1).value == "base":
            base_columns.append(number + 1)
    assert len(base_columns) == 2
    tab.cell(base_columns[1], headers.index("Expression") + 1).value = "20"
    book.save(path)
    book.close()
    import_review(project(native), path).apply()
    sql = (native / "models/nested.sql").read_text()
    assert "1 AS id" in sql and "20 AS id" in sql and "2 AS id" not in sql


def rows(path, sheet):
    book = load_workbook(path)
    tab = book[sheet]
    headers = [c.value for c in tab[1]]
    result = [dict(zip(headers, [c.value for c in row])) for row in tab.iter_rows(min_row=2)]
    book.close()
    return result


def test_reference_shorthand_display_and_scoped_writeback(native):
    path = export(native)
    base = next(r for r in rows(path, "gld") if r["Type"] == "STEP")
    assert base["Expression"] == "FROM ref.orders"
    output = next(r for r in rows(path, "slv") if r["Type"] == "OUTPUT")
    assert "source.raw.orders" in output["Expression"] and "{{" not in output["Expression"]
    assert import_review(project(native), path).apply() == []
    edit(path, "gld", "STEP", "base", Expression="FROM ref.orders WHERE id > 0")
    import_review(project(native), path).apply()
    assert "{{ ref('orders') }}" in (native / "models/gld/revenue.sql").read_text()


def test_scalar_macro_column_shorthand_expression_roundtrip(native):
    put(native, "macros/money.sql", "{% macro round_money(value) %}round({{ value }}, 2){% endmacro %}")
    put(native, "models/rounded.sql", "select {{ round_money('amount') }} as total from {{ ref('orders') }}")
    path = export(native)
    col = next(r for r in rows(path, "Models") if r["Type"] == "COLUMN")
    assert col["Name"] == "total" and col["Expression"] == "macro.round_money('amount')"
    edit(path, "Models", "COLUMN", "total", Expression="macro.round_money('amount + 1')", Description="Rounded total")
    import_review(project(native), path).apply()
    code = (native / "models/rounded.sql").read_text()
    assert "{{ round_money('amount + 1') }}" in code
    assert "extra_macro_" not in code and "{{ ref('orders') }}" in code


@pytest.mark.parametrize("expanded", [False, True])
def test_unknown_macro_is_template_not_a_guessed_column(native, expanded):
    put(native, "models/unknown.sql", "select {{ unknown('amount') }} from {{ ref('orders') }}")
    path = export(native, expand=expanded)
    items = rows(path, "Models")
    assert [r["Type"] for r in items] == ["TABLE", "TEMPLATE", "OUTPUT"]
    assert items[1]["Expression"] == "macro.unknown('amount')"
    assert import_review(project(native), path).apply() == []
    edit(path, "Models", "TEMPLATE", "unknown", Expression="macro.unknown('price')")
    import_review(project(native), path).apply()
    assert "{{ unknown('price') }}" in (native / "models/unknown.sql").read_text()


def test_multi_column_macro_expand_and_authored_call_writeback(native):
    put(native, "macros/columns.sql", "{% macro columns(value) %}id, {{ value }} as total{% endmacro %}")
    path_sql = put(native, "models/multi.sql", "-- Keep header\nselect {{ columns('amount') }} from {{ ref('orders') }}\n-- Keep footer\n")
    original = path_sql.read_text()
    path = export(native)
    assert not any(r["Type"] == "COLUMN" for r in rows(path, "Models"))
    edit(path, "Models", "TEMPLATE", "columns", Expression="macro.columns('amount * 2')")
    import_review(project(native), path).apply()
    assert path_sql.read_text() == original.replace("columns('amount')", "columns('amount * 2')")
    path = export(native, expand=True)
    items = rows(path, "Models")
    assert not any(r["Type"] == "TEMPLATE" for r in items)
    assert [(r["Name"], r["Expression"]) for r in items if r["Type"] == "COLUMN"] == [("id", "id"), ("total", "amount * 2")]
    assert import_review(project(native), path).apply() == []
    edit(path, "Models", "TABLE", "multi", **{"Authored SQL": original})
    import_review(project(native), path).apply()
    assert path_sql.read_text() == original


@pytest.mark.parametrize("kind,name,values", [
    ("COLUMN", "total", {"Expression": "amount * 99"}),
    ("OUTPUT", "OUTPUT", {"Expression": "FROM ref.orders WHERE id > 0"}),
    ("OUTPUT", "OUTPUT", {"Distinct": "true"}),
])
def test_generated_macro_sql_cannot_be_written_over_authored_calls(native, kind, name, values):
    put(native, "macros/columns.sql", "{% macro columns() %}id, amount as total{% endmacro %}")
    put(native, "models/multi.sql", "select {{ columns() }} from {{ ref('orders') }}")
    path = export(native, expand=True)
    edit(path, "Models", kind, name, **values)
    before = snapshot(native)
    with pytest.raises(SpecError, match="Read-only"):
        import_review(project(native), path)
    assert snapshot(native) == before


def test_scalar_macro_changes_since_selected_export_are_rejected(native):
    put(native, "macros/money.sql", "{% macro round_money(value) %}round({{ value }}, 2){% endmacro %}")
    put(native, "models/rounded.sql", "select {{ round_money('amount') }} as total from {{ ref('orders') }}")
    path = export(native, select=["rounded"])
    edit(path, "Models", "COLUMN", "total", Expression="macro.round_money('amount + 1')")
    put(native, "macros/money.sql", "{% macro round_money(value) %}id, amount{% endmacro %}")
    with pytest.raises(SpecError, match="changed since export"):
        import_review(project(native), path)


def test_multiple_template_call_edits_preserve_surrounding_sql(native):
    original = "-- Keep\nselect {{ first('a') }}, {{ second('b') }} from {{ ref('orders') }}\n"
    path_sql = put(native, "models/unknown.sql", original)
    path = export(native)
    edit(path, "Models", "TEMPLATE", "first", Expression="macro.first('c')")
    edit(path, "Models", "TEMPLATE", "second", Expression="macro.second('d')")
    import_review(project(native), path).apply()
    assert path_sql.read_text() == original.replace("first('a')", "first('c')").replace("second('b')", "second('d')")


def test_removed_context_columns_preserve_dbt_relationships_and_custom_metadata(native):
    put(native, "models/context.sql", "select id from {{ ref('orders') }}")
    put(native, "macros/value.sql", "{% macro value() %}1{% endmacro %}")
    put(native, "models/context.yml", """version: 2
models:
  - name: context
    config:
      meta:
        references: orders
        snapshot: custom note
    constraints:
      - type: foreign_key
        columns: [id]
        to: ref('orders')
        to_columns: [id]
    columns:
      - name: id
        data_tests:
          - relationships:
              arguments:
                to: ref('orders')
                field: id
""")
    path = export(native)
    book = load_workbook(path)
    for tab in book:
        if tab.title not in {"README", "_baseline"}:
            assert not {"Effective Config", "Snapshot", "References"} & {c.value for c in tab[1]}
    legend = {row[0].value: row[1].value for row in book["README"]}
    assert "Effective Config" not in " ".join(legend.values())
    assert "dbt project/package" in legend["Package"]
    assert "CASE WHEN" in legend["CASE template example"]
    book.close()
    table = next(r for r in rows(path, "Models") if r["Type"] == "TABLE")
    assert table["Package"] == "shop"
    assert json.loads(table["Constraints"])[0]["type"] == "foreign_key"
    assert json.loads(table["Config"])["meta"] == {"references": "orders", "snapshot": "custom note"}
    col = next(r for r in rows(path, "Models") if r["Type"] == "COLUMN")
    assert "relationships" in json.loads(col["Tests"])[0]
    assert import_review(project(native), path).apply() == []
    before = load_yaml(native / "models/context.yml")["models"][0]
    edit(path, "Models", "TABLE", "context", Description="Reviewed context")
    import_review(project(native), path).apply()
    after = load_yaml(native / "models/context.yml")["models"][0]
    assert after == {**before, "description": "Reviewed context"}


@pytest.mark.parametrize("folder", ["snapshots", "history/versions"])
def test_snapshot_table_fill_follows_configured_snapshot_roots(native, folder):
    with (native / "dbt_project.yml").open("a") as stream:
        stream.write(f"snapshot-paths: [{folder}]\n")
    put(native, f"{folder}/nested/order_history.sql", "select id from {{ ref('orders') }}")
    put(native, "models/snapshots/lookalike.sql", "select 1 as id")
    put(native, "seeds/sample.csv", "id\n1\n")
    path = export(native)
    book = load_workbook(path)
    tab = book["Snapshots · nested"]
    headers = [c.value for c in tab[1]]
    assert tab["A2"].value == "TABLE" and tab["B2"].value == f"{folder}/nested"
    assert all(c.fill.fgColor.rgb == "002B5F75" and c.font.color.rgb == "00FFFFFF" for c in tab[2])
    assert not tab.cell(2, headers.index("Description") + 1).protection.locked
    assert tab.cell(2, headers.index("Package") + 1).protection.locked
    for name in ("slv", "snapshots", "Seeds"):
        assert book[name]["A2"].fill.fgColor.rgb == "002F7D4F"
    book.close()
    assert import_review(project(native), path).apply() == []
    edit(path, "Snapshots · nested", "TABLE", "order_history", Description="Snapshot history")
    import_review(project(native), path).apply()
    assert load_yaml(native / f"{folder}/nested/_extra_properties.yml")["snapshots"][0]["description"] == "Snapshot history"


def test_case_when_scalar_template_column_roundtrip(native):
    macro = put(native, "macros/money.sql", "{% macro round_money(value) %}round({{ value }}, 2){% endmacro %}")
    original_macro = macro.read_bytes()
    put(native, "models/conditional.sql", "select case when amount > 0 then {{ round_money('amount') }} else 0 end as total from {{ ref('orders') }}")
    path = export(native)
    col = next(r for r in rows(path, "Models") if r["Type"] == "COLUMN")
    assert col["Expression"] == "CASE WHEN amount > 0 THEN macro.round_money('amount') ELSE 0 END"
    assert import_review(project(native), path).apply() == []
    edit(path, "Models", "COLUMN", "total",
         Expression="CASE WHEN amount >= 5 THEN macro.round_money('amount + 1') ELSE 0 END")
    import_review(project(native), path).apply()
    code = (native / "models/conditional.sql").read_text()
    assert "CASE" in code and "amount >= 5" in code and "ELSE 0" in code
    assert "{{ round_money('amount + 1') }}" in code and "{{ ref('orders') }}" in code
    assert "extra_macro_" not in code and macro.read_bytes() == original_macro


def test_case_when_expanded_column_metadata_preserves_authored_sql(native):
    put(native, "macros/money.sql", "{% macro round_money(value) %}round({{ value }}, 2){% endmacro %}")
    original = "-- Keep CASE\nselect case when amount > 0 then {{ round_money('amount') }} else 0 end as total from {{ ref('orders') }}\n"
    sql = put(native, "models/conditional.sql", original)
    path = export(native, expand=True)
    col = next(r for r in rows(path, "Models") if r["Type"] == "COLUMN")
    assert col["Expression"] == "CASE WHEN amount > 0 THEN ROUND(amount, 2) ELSE 0 END"
    assert not any(r["Type"] == "TEMPLATE" for r in rows(path, "Models"))
    assert import_review(project(native), path).apply() == []
    edit(path, "Models", "COLUMN", "total", Description="Conditional total")
    import_review(project(native), path).apply()
    assert sql.read_text() == original
    assert load_yaml(native / "models/_extra_properties.yml")["models"][0]["columns"][0]["description"] == "Conditional total"


@pytest.mark.parametrize("expanded", [False, True])
def test_case_when_unknown_template_call_does_not_guess_column_shape(native, expanded):
    original = "-- Keep CASE\nselect case when amount > 0 then {{ opaque('amount') }} else 0 end as total from {{ ref('orders') }}\n"
    sql = put(native, "models/conditional.sql", original)
    path = export(native, expand=expanded)
    items = rows(path, "Models")
    assert [r["Type"] for r in items] == ["TABLE", "TEMPLATE", "OUTPUT"]
    assert items[1]["Expression"] == "macro.opaque('amount')"
    assert import_review(project(native), path).apply() == []
    edit(path, "Models", "TEMPLATE", "opaque", Expression="macro.opaque('amount + 1')")
    import_review(project(native), path).apply()
    assert sql.read_text() == original.replace("opaque('amount')", "opaque('amount + 1')")


@pytest.mark.parametrize("body", ["round({{ value }}, 2)", "sum({{ value }})",
                                  "row_number() over (partition by {{ value }} order by id)",
                                  "{{ value }} as total"])
def test_one_column_macros_remain_column_expressions(native, body):
    put(native, "macros/value.sql", "{% macro value(value) %}" + body + "{% endmacro %}")
    suffix = "" if "as total" in body else " as total"
    sql = put(native, "models/mapped.sql", "select {{ value('amount') }}" + suffix + " from {{ ref('orders') }}")
    path = export(native)
    items = rows(path, "Models")
    assert not any(r["Type"] == "TEMPLATE" for r in items)
    col = next(r for r in items if r["Type"] == "COLUMN")
    assert col["Name"] == "total" and col["Expression"] == "macro.value('amount')"
    assert import_review(project(native), path).apply() == []
    edit(path, "Models", "COLUMN", "total", Expression="macro.value('amount + 1')")
    import_review(project(native), path).apply()
    assert "{{ value('amount + 1') }}" in sql.read_text()
    assert "extra_macro_" not in sql.read_text()
    assert sql.read_text().lower().count("as total") == (0 if "as total" in body else 1)


@pytest.mark.parametrize("expanded", [False, True])
@pytest.mark.parametrize("opaque", ["{{ unknown('amount') }}", "{{ runtime('amount') }}"])
def test_unresolved_call_does_not_hide_known_columns(native, expanded, opaque):
    put(native, "macros/value.sql", "{% macro value(value) %}round({{ value }}, 2){% endmacro %}")
    put(native, "macros/runtime.sql", "{% macro runtime(value) %}{{ adapter.get_columns_in_relation(value) }}{% endmacro %}")
    original = "select {{ value('amount') }} as total, " + opaque + " as mystery, id from {{ ref('orders') }}"
    sql = put(native, "models/mixed.sql", original)
    path = export(native, expand=expanded)
    items = rows(path, "Models")
    templates = [r for r in items if r["Type"] == "TEMPLATE"]
    assert len(templates) == 1 and templates[0]["Name"] in {"unknown", "runtime"}
    assert templates[0]["Reason"]
    columns = {r["Name"]: r["Expression"] for r in items if r["Type"] == "COLUMN"}
    assert columns == {"total": "ROUND(amount, 2)" if expanded else "macro.value('amount')", "id": "id"}
    assert not any("extra_macro_" in str(r) for r in items)
    assert import_review(project(native), path).apply() == []
    if expanded:
        edit(path, "Models", "COLUMN", "total", Description="Known output")
    else:
        edit(path, "Models", "COLUMN", "total", Expression="macro.value('amount + 1')")
    edit(path, "Models", "TEMPLATE", templates[0]["Name"], Expression=f"macro.{templates[0]['Name']}('price')")
    import_review(project(native), path).apply()
    code = sql.read_text()
    assert opaque.replace("'amount'", "'price'") in code
    assert ("{{ value('amount') }}" if expanded else "{{ value('amount + 1') }}") in code
    assert "extra_macro_" not in code


def test_multi_column_call_does_not_hide_single_column_call(native):
    put(native, "macros/value.sql", "{% macro value() %}sum(amount){% endmacro %}{% macro fields() %}id, amount{% endmacro %}")
    put(native, "models/mixed.sql", "select {{ value() }} as total, {{ fields() }} from {{ ref('orders') }}")
    path = export(native)
    items = rows(path, "Models")
    assert [r["Name"] for r in items if r["Type"] == "TEMPLATE"] == ["fields"]
    assert [(r["Name"], r["Expression"]) for r in items if r["Type"] == "COLUMN"] == [("total", "macro.value()")]
    assert import_review(project(native), path).apply() == []


def test_expanded_macro_derives_actual_sql_lineage(native):
    put(native, "macros/fields.sql", "{% macro fields() %}id, amount * 2 as doubled{% endmacro %}")
    put(native, "models/mapped.sql", "select {{ fields() }} from {{ ref('orders') }}")
    export(native, expand=True)
    tables, _ = read_review(native / "extra_review/review.xlsx")
    cols = {r["column"]: r for r in tables["columns"] if r["name"] == "mapped"}
    assert set(cols) == {"id", "doubled"}
    assert json.loads(cols["doubled"]["upstream_columns"]) == [{"resource_id": "model.shop.orders", "column": "amount"}]


def test_partial_column_edit_cannot_introduce_unknown_output_shape(native):
    put(native, "macros/value.sql", "{% macro value() %}1{% endmacro %}")
    put(native, "models/mixed.sql", "select {{ value() }} as total, {{ unknown() }}")
    path = export(native)
    edit(path, "Models", "COLUMN", "total", Expression="macro.unknown()")
    before = snapshot(native)
    with pytest.raises(SpecError, match="resolved unaliased expression"):
        import_review(project(native), path)
    assert snapshot(native) == before


def test_resolved_clause_macro_expands_without_template_row(native):
    put(native, "macros/filter.sql", "{% macro filter_rows() %}where amount > 0{% endmacro %}")
    put(native, "models/filtered.sql", "select id from {{ ref('orders') }} {{ filter_rows() }}")
    path = export(native)
    template = next(r for r in rows(path, "Models") if r["Type"] == "TEMPLATE")
    assert template["Name"] == "filter_rows" and "SQL clauses" in template["Reason"]
    path = export(native, expand=True)
    items = rows(path, "Models")
    assert not any(r["Type"] == "TEMPLATE" for r in items)
    assert [(r["Name"], r["Expression"]) for r in items if r["Type"] == "COLUMN"] == [("id", "id")]
    clauses = next(r["Expression"] for r in items if r["Type"] == "OUTPUT")
    assert "WHERE amount > 0" in " ".join(clauses.split())
    assert import_review(project(native), path).apply() == []


def test_partial_cte_column_and_template_edits_keep_projection_bindings(native):
    put(native, "macros/value.sql", "{% macro value(value) %}sum({{ value }}){% endmacro %}")
    sql = put(native, "models/mixed.sql", "with base as (select {{ unknown() }}, {{ value('amount') }} as total from {{ ref('orders') }}) select total from base")
    path = export(native)
    items = rows(path, "Models")
    assert [r["Expression"] for r in items if r["Type"] == "COLUMN"] == ["macro.value('amount')", "total"]
    edit(path, "Models", "COLUMN", "total", Expression="macro.value('amount + 1')")
    edit(path, "Models", "TEMPLATE", "unknown", Expression="macro.unknown('new')")
    import_review(project(native), path).apply()
    code = sql.read_text()
    assert "{{ unknown('new') }}" in code and "{{ value('amount + 1') }}" in code
    assert "extra_macro_" not in code
