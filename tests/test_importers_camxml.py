# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""SolidCAM and hyperMILL importer tests.

Both export self-describing `<param name= value=>` XML. Fixtures are single-tool
exports of the same tool (Kennametal HARVI 1/4" endmill), so the two parse to the
same geometry from different schemas."""
from pathlib import Path

import pytest

from loobric import importers
from loobric.importers import hypermill, solidcam

FIXTURES = Path(__file__).parent / "fixtures" / "importers"

EXPECTED_GEOM = {
    "shape": {"value": "endmill"},
    "diameter": {"value": 6.35, "unit": "mm"},
    "shank_diameter": {"value": 6.35, "unit": "mm"},
    "length": {"value": 63.5, "unit": "mm"},
    "cutting_edge_height": {"value": 19.05, "unit": "mm"},
    "flutes": {"value": 4},
}


def test_solidcam_parse():
    draft = solidcam.parse(FIXTURES / "solidcam.xml")[0]
    assert draft.name == "END MILL HARVI I TE 1/4X1/4X3/4X2 1/2 S"   # "6676918_" stripped
    assert draft.manufacturer == "Kennametal"                       # from message2
    assert draft.product_code == "6676918"
    assert draft.source_class == "EndMill"
    assert draft.fields["geometry"] == EXPECTED_GEOM
    assert draft.source_actor == "solidcam-import"
    # the free-text messages survive in raw (lossless)
    assert "message2" in draft.raw


def test_hypermill_parse():
    draft = hypermill.parse(FIXTURES / "hypermill.xml")[0]
    assert draft.name == "HARVI I TE 1/4X1/4X3/4X2 1/2 S - 6676918 - KH"
    assert draft.manufacturer == "Kennametal"                       # named param
    assert draft.product_code == "6676918"                          # orderingCode
    assert draft.source_class == "endMill"
    assert draft.fields["geometry"] == EXPECTED_GEOM
    assert draft.source_actor == "hypermill-import"


def test_both_cam_formats_agree_on_geometry():
    sc = solidcam.parse(FIXTURES / "solidcam.xml")[0].fields["geometry"]
    hm = hypermill.parse(FIXTURES / "hypermill.xml")[0].fields["geometry"]
    assert sc == hm == EXPECTED_GEOM


@pytest.mark.parametrize("fixture,expected_format", [
    ("solidcam.xml", "solidcam"),
    ("hypermill.xml", "hypermill"),
    ("din4000-82_2013.xml", "din4000-xml"),   # ToolsUnited <Tool-Data> root
    ("din4000-82.csv", "din4000-csv"),
    ("iso13399.p21", "p21"),
])
def test_dispatcher_routes_by_format(fixture, expected_format):
    assert importers.parse(FIXTURES / fixture)[0].source_format == expected_format
