# MIT License
# Copyright (c) 2026 sliptonic
# SPDX-License-Identifier: MIT
"""CAM-library importer tests: Vectric .vtdb, SprutCam .db, CAMotics JSON.

The SQLite fixtures are built synthetically per-test (same tables/columns as
the real files — schema decoded on MASSO forum thread 4563 and cross-checked
against the Cadence ground-truth dump — but no vendor data committed). Values
mirror the Cadence "Mini Jenny" row so the preset math is checked against a
real-world case.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from loobric import importers
from loobric.importers import camotics, sprutcam, vectric
from loobric.importers.base import LibraryToolDraft
from loobric.importers.run import import_library_drafts

FIXTURES = Path(__file__).parent / "fixtures" / "importers"


# -- fixture builders ---------------------------------------------------------

def make_vtdb(path, *, with_material_row=True, tool_type=1, name_format=None):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE tool_geometry (
            id TEXT PRIMARY KEY, name_format TEXT, notes TEXT,
            tool_type INTEGER, units INTEGER, diameter REAL,
            included_angle REAL, flat_diameter REAL, num_flutes INTEGER,
            flute_length REAL, tip_radius REAL);
        CREATE TABLE tool_cutting_data (
            id TEXT PRIMARY KEY, rate_units INTEGER, feed_rate REAL,
            plunge_rate REAL, spindle_speed REAL, stepdown REAL,
            stepover REAL, clear_stepover REAL, length_units INTEGER,
            tool_number INTEGER);
        CREATE TABLE tool_entity (
            id TEXT PRIMARY KEY, material_id TEXT, machine_id TEXT,
            tool_geometry_id TEXT, tool_cutting_data_id TEXT);
        CREATE TABLE material (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE machine (id TEXT PRIMARY KEY, name TEXT);
    """)
    con.execute("INSERT INTO tool_geometry VALUES "
                "('geo-1', ?, NULL, ?, 1, 0.125, NULL, NULL, 2, 0.5, NULL)",
                (name_format or '1/8" Mini Jenny Compression', tool_type))
    # master cutting data (material NULL) carries the tool number
    con.execute("INSERT INTO tool_cutting_data VALUES "
                "('cut-master', 4, NULL, NULL, NULL, NULL, NULL, NULL, 0, 7)")
    con.execute("INSERT INTO tool_entity VALUES "
                "('ent-master', NULL, 'mach-1', 'geo-1', 'cut-master')")
    if with_material_row:
        con.execute("INSERT INTO tool_cutting_data VALUES "
                    "('cut-acrylic', 4, 100, 65, 19000, 0.08, 0.05, NULL, 1, NULL)")
        con.execute("INSERT INTO tool_entity VALUES "
                    "('ent-acrylic', 'mat-1', 'mach-1', 'geo-1', 'cut-acrylic')")
        con.execute("INSERT INTO material VALUES ('mat-1', 'Acrylic')")
        con.execute("INSERT INTO machine VALUES ('mach-1', 'Journeyman')")
    con.commit()
    con.close()
    return path


def make_sprutcam_db(path, *, with_material=False):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE ISTMillToolAccessor (
            object_id INTEGER PRIMARY KEY, ID INTEGER, NAME TEXT,
            COMMENT TEXT, `MILL TYPE` INTEGER, D REAL, R REAL, L REAL,
            `TEETH NUMBER` INTEGER, `MEASUREMENT UNITS` INTEGER,
            `ROTATIONS PER MIN.` REAL, FEEDRATE REAL, `CUTTING SPEED` REAL,
            SHANKDIAMETER REAL, TOOLNUM INTEGER, TOOLID TEXT,
            BESTMATERIAL INTEGER);
        CREATE TABLE ISTMaterialsAccessor (
            object_id INTEGER PRIMARY KEY, ID INTEGER, Name TEXT);
    """)
    con.execute("INSERT INTO ISTMillToolAccessor VALUES "
                "(1, 2, '6mm Cylindrical mill', '', 0, 6.0, 0.0, 64.0, 2, 0, "
                "12000, 2000, 226.19, 6.0, 1, '1', ?)",
                (90002 if with_material else 0,))
    con.execute("INSERT INTO ISTMillToolAccessor VALUES "
                "(2, 7, 'Saw blade', '', 2, 37.0, 0.0, 50.0, 2, 0, "
                "15000, 1000, 1743.58, 12.0, 7, '', 0)")
    if with_material:
        con.execute("INSERT INTO ISTMaterialsAccessor VALUES (1, 90002, 'Alu')")
    con.commit()
    con.close()
    return path


def leafmap(draft):
    return {path: (value, unit) for path, value, unit in draft.asserts}


# -- Vectric ------------------------------------------------------------------

def test_vectric_parse(tmp_path):
    drafts = importers.parse(make_vtdb(tmp_path / "tools.vtdb"))
    assert len(drafts) == 1
    d = drafts[0]
    assert isinstance(d, LibraryToolDraft)
    assert d.client_item_id == "geo-1"
    assert d.client_name == "vectric"
    assert d.name == '1/8" Mini Jenny Compression'
    geom = leafmap(d)
    assert geom["geometry.diameter"] == (0.125, "in")
    assert geom["geometry.cutting_edge_height"] == (0.5, "in")
    assert geom["geometry.flutes"] == (2, None)
    assert geom["geometry.shape"] == ("endmill", None)
    assert d.data["properties"]["tool_number"] == 7    # from the master row


def test_vectric_preset_math(tmp_path):
    d = importers.parse(make_vtdb(tmp_path / "tools.vtdb"))[0]
    assert len(d.presets) == 1
    p = d.presets[0]
    assert p["origin"] == "vectric"
    assert p["label"] == "Acrylic @ Journeyman"
    assert p["material"] == {"name": "Acrylic"}
    # vc = pi * 3.175mm * 19000 / 1000 ; fz = (100 in/min -> mm/min) / (n * z)
    assert p["vc"]["value"] == pytest.approx(189.5, abs=0.1)
    assert p["fz"]["value"] == pytest.approx(2540.0 / (19000 * 2), abs=1e-4)
    assert p["ratio"]["value"] == pytest.approx(0.65)
    assert p["extras"]["stepdown"] == {"value": 0.08, "unit": "in"}


def test_vectric_no_material_no_presets(tmp_path):
    d = importers.parse(make_vtdb(tmp_path / "t.vtdb",
                                  with_material_row=False))[0]
    assert d.presets == []


def test_vectric_unknown_type_has_no_shape(tmp_path):
    # tool_type 5 (Tapered Ball Nose) has no unambiguous canonical silhouette:
    # honest absence, never a guess (the endmill guard).
    d = importers.parse(make_vtdb(tmp_path / "t.vtdb", tool_type=5))[0]
    assert "geometry.shape" not in leafmap(d)
    assert d.data["tool_type"] == "Tapered Ball Nose"


def test_vectric_name_template_expansion(tmp_path):
    d = importers.parse(make_vtdb(
        tmp_path / "t.vtdb",
        name_format="{Tool Type} {Diameter|F} {Units Short} {Num Flutes}FL"))[0]
    assert d.name == 'End Mill 1/8 in 2FL'


# -- SprutCam -----------------------------------------------------------------

def test_sprutcam_parse(tmp_path):
    drafts = importers.parse(make_sprutcam_db(tmp_path / "Default_tools.db"))
    assert [d.name for d in drafts] == ["6mm Cylindrical mill", "Saw blade"]
    mill, saw = drafts
    assert mill.client_item_id == "1"          # TOOLID when present
    assert saw.client_item_id == "row:2"       # object_id fallback
    geom = leafmap(mill)
    assert geom["geometry.diameter"] == (6.0, "mm")
    assert geom["geometry.length"] == (64.0, "mm")
    assert geom["geometry.shank_diameter"] == (6.0, "mm")
    assert geom["geometry.flutes"] == (2, None)
    assert geom["geometry.shape"] == ("endmill", None)
    assert leafmap(saw)["geometry.shape"] == ("slittingsaw", None)


def test_sprutcam_presets_need_material(tmp_path):
    # The dangling-material case (as in the real sample library): F&S stay in
    # the preserved properties, no contribution below the floor.
    drafts = importers.parse(make_sprutcam_db(tmp_path / "a.db"))
    assert all(d.presets == [] for d in drafts)

    drafts = importers.parse(make_sprutcam_db(tmp_path / "b.db",
                                              with_material=True))
    p = drafts[0].presets[0]
    assert p["material"] == {"name": "Alu"}
    assert p["vc"]["value"] == pytest.approx(226.19)
    assert p["fz"]["value"] == pytest.approx(2000 / (12000 * 2), abs=1e-4)


# -- CAMotics -----------------------------------------------------------------

def test_camotics_parse():
    drafts = importers.parse(FIXTURES / "camotics.json")
    assert len(drafts) == 3
    flat, ball, vee = drafts
    assert flat.name == "1/4in flat endmill"
    assert leafmap(flat)["geometry.diameter"] == (6.35, "mm")
    assert leafmap(flat)["geometry.shape"] == ("endmill", None)
    assert ball.name == "T2 Ballnose"          # no description — synthesized
    assert leafmap(ball)["geometry.diameter"] == (0.25, "in")
    assert leafmap(ball)["geometry.shape"] == ("ballend", None)
    # Conical has no unambiguous canonical shape: honest absence.
    assert "geometry.shape" not in leafmap(vee)
    assert vee.data["properties"]["shape"] == "Conical"


def test_camotics_project_file(tmp_path):
    doc = {"units": "metric",
           "tools": {"5": {"units": "metric", "shape": "Cylindrical",
                           "diameter": 3.0, "length": 38}}}
    f = tmp_path / "job.camotics"
    f.write_text(json.dumps(doc))
    drafts = camotics.parse(f)
    assert drafts[0].client_item_id == "tool:5"


def test_camotics_rejects_fusion_json(tmp_path):
    f = tmp_path / "library.json"
    f.write_text(json.dumps({"data": [{"guid": "x"}], "version": 2}))
    with pytest.raises(ValueError, match="loobric-fusion"):
        importers.parse(f)


# -- dispatch + driver --------------------------------------------------------

def test_dispatch_unknown_sqlite(tmp_path):
    path = tmp_path / "other.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE unrelated (x)")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="unrecognized SQLite"):
        importers.parse(path)


class StubClient:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def sync_tool_records(self, client, items, client_version=""):
        self.calls.append((client, items, client_version))
        return self.results


def test_import_library_drafts(tmp_path):
    drafts = importers.parse(make_vtdb(tmp_path / "t.vtdb"))
    stub = StubClient([{"client_item_id": "geo-1", "id": "rec-1",
                        "result": "created", "presets_contributed": 1}])
    events = []
    report = import_library_drafts(
        stub, drafts, on_event=lambda k, d, i: events.append((k, i)))

    client, items, _ = stub.calls[0]
    assert client == "vectric"
    item = items[0]
    assert item["client_item_id"] == "geo-1"
    assert item["data"]["format"] == "vectric"
    assert {"path": "geometry.diameter", "value": 0.125, "unit": "in"} \
        in item["asserts"]
    assert item["presets"][0]["label"] == "Acrylic @ Journeyman"

    assert [d.name for d, _ in report.created] == [drafts[0].name]
    assert report.presets_contributed == 1
    assert events == [("created", "rec-1")]


def test_import_library_drafts_error_result():
    d = LibraryToolDraft(client_item_id="x", name="broken", data={})
    stub = StubClient([{"client_item_id": "x", "result": "error",
                        "error": "no door"}])
    report = import_library_drafts(stub, [d], client_name="vectric")
    assert report.failed == [(d, "no door")]
