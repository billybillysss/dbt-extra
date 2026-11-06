"""Forest + Paper workbook theme and cell presentation."""

import math
from xml.etree import ElementTree as ET

from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.writer.theme import theme_xml

from dbt_extra.errors import SpecError
from dbt_extra.review.xlsx.layout import CONTEXT_HEADERS, ROW_ID


# Forest + Paper: https://bigexcelenergy.com/excel-dashboard-color-palette/
# OUTPUT is a derived pale-sage tint; all column surfaces stay pure white.
PALETTE = {"canvas": "F7F8F5", "surface": "FFFFFF", "text": "1F2723", "muted": "65726A",
           "accent": "2F7D4F", "support": "2B5F75", "output": "EAF2ED"}
CHART_COLORS = ("2F7D4F", "2B5F75", "B56727", "6B3FA0", "007C78", "B6424E")


def forest_paper_theme():
    """Embed matching Office theme slots for Excel's theme color picker."""
    namespace = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ET.register_namespace("a", namespace)
    root = ET.fromstring(theme_xml)
    root.set("name", "Forest + Paper")
    scheme = root.find(f".//{{{namespace}}}clrScheme")
    scheme.set("name", "Forest + Paper")
    colors = {"dk1": PALETTE["text"], "lt1": PALETTE["surface"], "dk2": PALETTE["support"],
              "lt2": PALETTE["canvas"], "hlink": PALETTE["accent"], "folHlink": PALETTE["muted"],
              **{f"accent{i}": color for i, color in enumerate(CHART_COLORS, 1)}}
    for slot in scheme:
        name = slot.tag.rsplit("}", 1)[1]
        slot.clear()
        ET.SubElement(slot, f"{{{namespace}}}srgbClr", val=colors[name])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def style_legend(legend):
    legend.column_dimensions["A"].width = 26
    legend.column_dimensions["B"].width = 112
    legend.sheet_view.showGridLines = False
    for row in legend:
        legend.row_dimensions[row[0].row].height = 44
        for cell in row:
            cell.data_type = "s"
            cell.font = Font(name="Arial", size=10, color=PALETTE["accent"] if cell.column == 1 else PALETTE["text"], bold=cell.column == 1)
            cell.fill = PatternFill("solid", fgColor=PALETTE["canvas"] if cell.column == 1 else PALETTE["surface"])
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def write_sheet(book, spec):
    sheet = book.create_sheet(spec["name"])
    headers = spec["headers"]
    sheet.append(headers)
    widths = {"Type": 13, "Path": 30, "Name": 30, "Distinct": 10, "Key": 14,
              "Expression": 80, "Data Type": 20, "Description": 48,
              "Config": 45, "Constraints": 32, "Tests": 34, "Meta": 36, "Properties": 44, "Authored SQL": 80,
              "Scope": 48, "Reason": 48, "Source File": 42}
    for index, header in enumerate(headers, 1):
        dimension = sheet.column_dimensions[get_column_letter(index)]
        dimension.width = widths.get(header, 24)
        dimension.hidden = header in {ROW_ID, "Authored SQL"}
    for item in spec["rows"]:
        values = {**item["values"], ROW_ID: item["id"]}
        if any(len(str(value)) > 32767 for value in values.values()):
            raise SpecError(f"XLSX cell limit exceeded in {spec['name']}; use CSV or JSON for large SQL")
        sheet.append([values.get(h, "") for h in headers])
        row_number = sheet.max_row
        sheet.row_dimensions[row_number].outlineLevel = item["level"]
        kind = item["kind"]
        dark = kind in {"TABLE", "SOURCE", "MACRO"}
        fill = (PALETTE["support"] if kind == "TABLE" and spec["category"] == "Snapshots" else
                PALETTE["accent"] if dark else PALETTE["output"] if kind == "OUTPUT" else
                PALETTE["canvas"] if kind == "STEP" else PALETTE["surface"])
        editable_headers = set(item["fields"]) | (set(item["props"]) | {"Properties"} if item["target"] and item["metadata_editable"] else set())
        height = 1
        for cell, header in zip(sheet[row_number], headers, strict=True):
            editable = item["editable"] and header in editable_headers
            cell.data_type = "s"
            context = header in CONTEXT_HEADERS + [ROW_ID, "Path", "Key"]
            color = PALETTE["surface"] if dark else PALETTE["accent"] if editable else PALETTE["muted"] if context else PALETTE["text"]
            cell.font = Font(name="Arial", size=10, color=color, bold=kind in {"TABLE", "SOURCE", "MACRO", "STEP", "OUTPUT"})
            cell.fill = PatternFill("solid", fgColor=fill)
            cell.alignment = Alignment(vertical="top", wrap_text=True, indent=item["level"] if header == "Name" else 0)
            cell.protection = Protection(locked=not editable)
            if header not in {ROW_ID, "Authored SQL"}:
                width = max(8, widths.get(header, 24) - 2)
                height = max(height, sum(max(1, math.ceil(len(line) / width)) for line in str(cell.value or "").split("\n")))
        sheet.row_dimensions[row_number].height = min(150, max(24, 14 * height + 8))
    for cell in sheet[1]:
        cell.data_type = "s"
        cell.font = Font(name="Arial", size=10, bold=True, color=PALETTE["surface"])
        cell.fill = PatternFill("solid", fgColor=PALETTE["text"])
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "D2" if "Type" in headers else "C2"
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.outlinePr.summaryRight = False
    sheet.sheet_properties.outlinePr.summaryBelow = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.sheet_properties.tabColor = PALETTE["support"] if spec["category"] == "Config" else PALETTE["accent"]
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers) - 1)}{sheet.max_row}"
    sheet.print_title_rows = "1:1"
    visible_end = len(headers) - (2 if "Authored SQL" in headers else 1)
    sheet.print_area = f"A1:{get_column_letter(visible_end)}{sheet.max_row}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
