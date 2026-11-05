"""Preserve the maintainer-supplied icon and accessible README references."""

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"
SVG = "{http://www.w3.org/2000/svg}"
PATHS = ["M18 18H110V46H74V74H46V110H18Z", "M54 110V82H82V54H110V110Z"]
PALETTES = {
    "dbt-extra-mark.svg": ["#0D9488", "#38BDF8"],
    "dbt-extra-mark-dark.svg": ["#0D9488", "#38BDF8"],
    "dbt-extra-mark-mono.svg": ["#0F172A", "#0F172A"],
}


@pytest.mark.parametrize("name", PALETTES)
def test_supplied_icon_geometry_palette_and_accessibility(name):
    root = ET.parse(ASSETS / name).getroot()
    assert root.tag == SVG + "svg"
    assert root.attrib["viewBox"] == "0 0 128 128"
    assert (root.attrib["width"], root.attrib["height"]) == ("128", "128")
    assert root.attrib["role"] == "img"
    assert root.attrib["aria-labelledby"].split() == ["title", "description"]
    assert root.find(SVG + "title").text == "dbt-extra symbol"
    assert root.find(SVG + "desc").text.strip()
    symbol = root.find(f"{SVG}g[@id='modular-joint']")
    assert [path.attrib["d"] for path in symbol] == PATHS
    assert [path.attrib["fill"] for path in symbol] == PALETTES[name]
    allowed = {SVG + tag for tag in ("svg", "title", "desc", "g", "path")}
    ids = []
    for element in root.iter():
        assert element.tag in allowed
        if "id" in element.attrib:
            ids.append(element.attrib["id"])
        for key, value in element.attrib.items():
            assert not key.lower().startswith("on")
            assert key not in {"href", "style", "{http://www.w3.org/1999/xlink}href"}
            assert "url(" not in value.lower()
    assert ids == ["title", "description", "modular-joint"]


def test_light_dark_symbol_is_identical_and_readme_uses_both():
    symbols = [ET.parse(ASSETS / name).getroot().find(f"{SVG}g[@id='modular-joint']")
               for name in ("dbt-extra-mark.svg", "dbt-extra-mark-dark.svg")]
    assert ET.tostring(symbols[0]) == ET.tostring(symbols[1])
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'srcset="docs/assets/dbt-extra-mark-dark.svg"' in readme
    assert 'src="docs/assets/dbt-extra-mark.svg"' in readme
    assert 'alt="dbt-extra — Modular joint icon"' in readme
