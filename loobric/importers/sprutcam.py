# MIT License
# Copyright (c) 2026 sliptonic
# SPDX-License-Identifier: MIT
"""SprutCam tool-library reader (plain SQLite ``.db``).

Milling tools live flat in ``ISTMillToolAccessor`` (schema decoded from a real
library shared on MASSO forum thread 4563; the four identity columns match the
extraction Breezy's field-tested converter uses). Geometry and F&S are richer
than that four-column floor, so we take what the source explicitly states:
diameter ``D``, corner radius ``R``, length ``L``, teeth, shank diameter, and
the spindle/feed values — normalized to vc/fz/ratio only when a material can be
resolved from ``ISTMaterialsAccessor`` (usually it cannot: the sample library's
material ids dangle — those rows keep their F&S in the preserved source
properties instead). User library → ToolInstanceRecords. Stdlib ``sqlite3``.
"""
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loobric.importers.base import LibraryToolDraft

SOURCE_FORMAT = "sprutcam"
CLIENT_NAME = "sprutcam"
ORIGIN = "sprutcam"

# `MILL TYPE` -> canonical shape. Only the three values verified against real
# rows (0 "Cylindrical mill", 1 "Spherical mill", 2 "saw blade") are mapped;
# any other value keeps the honest absence.
TYPE_TO_SHAPE = {0: "endmill", 1: "ballend", 2: "slittingsaw"}

# `MEASUREMENT UNITS` / header `LIBUNITS`: 0 = mm, 1 = inch (same convention
# as the Vectric column, cross-checked against the metric sample library).
_LEN_UNITS = {0: "mm", 1: "in"}


def sniff(table_names) -> bool:
    """True if this SQLite table set looks like a SprutCam tool library."""
    return "istmilltoolaccessor" in {t.lower() for t in table_names}


def parse(path: Union[str, Path]) -> List[LibraryToolDraft]:
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [_draft(con, dict(r)) for r in
                con.execute("SELECT * FROM ISTMillToolAccessor").fetchall()]
    finally:
        con.close()


def _draft(con, row: Dict[str, Any]) -> LibraryToolDraft:
    unit = _LEN_UNITS.get(row.get("MEASUREMENT UNITS"))
    name = (row.get("NAME") or row.get("COMMENT") or "(unnamed)").strip()

    asserts = []
    if unit is not None:
        for col, path in (("D", "geometry.diameter"),
                          ("L", "geometry.length"),
                          ("SHANKDIAMETER", "geometry.shank_diameter")):
            val = _num(row.get(col))
            if val:
                asserts.append((path, val, unit))
    teeth = _num(row.get("TEETH NUMBER"))
    if teeth:
        asserts.append(("geometry.flutes", int(teeth), None))
    shape = TYPE_TO_SHAPE.get(row.get("MILL TYPE"))
    if shape:
        asserts.append(("geometry.shape", shape, None))

    item_id = str(row.get("TOOLID") or "").strip() or f"row:{row['object_id']}"
    data = {
        "format": SOURCE_FORMAT,
        "properties": {k: v for k, v in row.items() if v not in (None, "")},
    }
    return LibraryToolDraft(
        client_item_id=item_id, name=name, data=data, asserts=asserts,
        presets=_presets(con, row, unit),
        source_format=SOURCE_FORMAT, client_name=CLIENT_NAME)


def _presets(con, row: Dict[str, Any], unit: Optional[str]
             ) -> List[Dict[str, Any]]:
    """One contribution when the floor is met: a resolvable material plus the
    row's engineering values. SprutCam stores vc directly (`CUTTING SPEED`,
    m/min) alongside RPM and feed."""
    material = _material_name(con, row.get("BESTMATERIAL"))
    if not material or unit != "mm":
        return []                       # below the floor / unverified units
    n = _num(row.get("ROTATIONS PER MIN."))
    feed = _num(row.get("FEEDRATE"))
    vc = _num(row.get("CUTTING SPEED"))
    teeth = _num(row.get("TEETH NUMBER"))

    body: Dict[str, Any] = {"origin": ORIGIN, "label": material,
                            "material": {"name": material}}
    if vc:
        body["vc"] = {"value": round(vc, 2), "unit": "m/min"}
    if n and feed is not None and teeth:
        body["fz"] = {"value": round(feed / (n * teeth), 4), "unit": "mm"}
    if not any(k in body for k in ("vc", "fz")):
        return []
    return [body]


def _material_name(con, material_id) -> Optional[str]:
    if not material_id:
        return None
    try:
        r = con.execute("SELECT Name FROM ISTMaterialsAccessor WHERE ID = ?",
                        (material_id,)).fetchone()
    except sqlite3.Error:
        return None
    return r["Name"] if r and r["Name"] else None


def _num(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
