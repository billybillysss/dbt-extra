"""Validate local SVG assets and their accessibility metadata."""

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"
SVG = "{http://www.w3.org/2000/svg}"


@pytest.mark.parametrize("path", sorted(ASSETS.glob("*.svg")), ids=lambda path: path.name)
def test_svg_assets_are_accessible_and_self_contained(path):
    root = ET.parse(path).getroot()
    assert root.tag == SVG + "svg"
    view_box = [float(value) for value in root.attrib["viewBox"].split()]
    assert len(view_box) == 4 and all(value > 0 for value in view_box[2:])
    assert root.attrib["role"] == "img"
    assert root.find(SVG + "title").text.strip()
    assert root.find(SVG + "desc").text.strip()
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
    assert len(ids) == len(set(ids))
    labels = root.attrib["aria-labelledby"].split()
    assert labels
    for label in labels:
        element = root.find(f".//*[@id='{label}']")
        assert element is not None and "".join(element.itertext()).strip()
