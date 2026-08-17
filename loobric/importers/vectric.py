# MIT License
# Copyright (c) 2026 sliptonic
# SPDX-License-Identifier: MIT
"""Vectric tool-database reader (`.vtdb` — Aspire / VCarve / Cut2D).

A `.vtdb` is a plain, unencrypted SQLite file. The master geometry rows come
from the community-validated join (MASSO forum thread 4563; recovered verbatim
from Breezy's field-tested converter): ``tool_geometry ⋈ tool_entity ⋈
tool_cutting_data WHERE tool_entity.material_id IS NULL``. Rows *with* a
material are that tool's per-material/per-machine cutting data — they become
preset contributions on the same record ((origin, label) identity,
docs/PRESETS.md).

These are the user's own tools, not a manufacturer catalog: no natural key, so
they land as ToolInstanceRecords keyed by the ``tool_geometry.id`` GUID.
Stdlib ``sqlite3`` only.
"""
import math
import sqlite3
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loobric.importers.base import LibraryToolDraft

SOURCE_FORMAT = "vectric"
CLIENT_NAME = "vectric"
ORIGIN = "vectric"

# tool_geometry.tool_type — the 16-entry enum, decoded twice independently on
# the MASSO forum (posts #51/#52). The declared type is the ONLY thing shape is
# asserted from; unknown entries keep the honest absence.
TOOL_TYPES = {
    0: "Ball Nose", 1: "End Mill", 2: "Radiused End Mill", 3: "V-Bit",
    4: "Engraving", 5: "Tapered Ball Nose", 6: "Drill", 8: "Form Tool",
    9: "Diamond Drag", 12: "Laser", 14: "Thread Mill", 15: "Multi Thread Mill",
}
# tool_type -> canonical geometry.shape (FreeCAD-rooted vocabulary; only types
# with an unambiguous silhouette are mapped — Engraving/Tapered/Form/… are not).
TYPE_TO_SHAPE = {
    0: "ballend", 1: "endmill", 2: "bullnose", 3: "vbit", 6: "drill",
    14: "threadmill", 15: "threadmill",
}

# tool_geometry.units / tool_cutting_data.length_units: 0 = mm, 1 = inch
# (verified against the Cadence ground-truth dump and Breezy's converter).
_LEN_UNITS = {0: "mm", 1: "in"}
_TO_MM = {0: 1.0, 1: 25.4}

# tool_cutting_data.rate_units — Vectric's feed-unit dropdown order (V10.5+
# docs); index 4 sanity-checked against the Cadence sample (US machine,
# 100 in/min on a 1/8" compression bit). Value -> mm/min conversion factor.
_RATE_TO_MM_MIN = {
    0: 60.0,        # mm/sec
    1: 1.0,         # mm/min
    2: 1000.0,      # m/min
    3: 1524.0,      # inches/sec
    4: 25.4,        # inches/min
    5: 304.8,       # feet/min
}


def sniff(table_names) -> bool:
    """True if this SQLite table set looks like a Vectric tool database."""
    lowered = {t.lower() for t in table_names}
    return "tool_geometry" in lowered and "tool_entity" in lowered


def parse(path: Union[str, Path]) -> List[LibraryToolDraft]:
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return _parse_con(con)
    finally:
        con.close()


def _parse_con(con) -> List[LibraryToolDraft]:
    masters = con.execute("""
        SELECT tool_geometry.id AS geometry_id, tool_geometry.*,
               tool_cutting_data.tool_number
        FROM tool_geometry
        INNER JOIN (tool_cutting_data
                    INNER JOIN tool_entity
                    ON tool_cutting_data.id = tool_entity.tool_cutting_data_id)
        ON tool_geometry.id = tool_entity.tool_geometry_id
        WHERE tool_entity.material_id IS NULL
    """).fetchall()

    drafts = []
    for row in masters:
        drafts.append(_draft(con, dict(row)))
    return drafts


def _draft(con, row: Dict[str, Any]) -> LibraryToolDraft:
    unit = _LEN_UNITS.get(row.get("units"))
    tool_type = row.get("tool_type")
    name = _expand_name_format(row.get("name_format") or "", row) or "(unnamed)"

    asserts = []
    if unit is not None:
        for col, path in (("diameter", "geometry.diameter"),
                          ("flute_length", "geometry.cutting_edge_height")):
            val = row.get(col)
            if val not in (None, "", 0):
                asserts.append((path, float(val), unit))
    flutes = row.get("num_flutes")
    if flutes not in (None, "", 0):
        asserts.append(("geometry.flutes", int(flutes), None))
    shape = TYPE_TO_SHAPE.get(tool_type)
    if shape:
        asserts.append(("geometry.shape", shape, None))

    presets = _presets(con, row) if unit is not None else []

    data = {
        "format": SOURCE_FORMAT,
        "tool_type": TOOL_TYPES.get(tool_type, tool_type),
        "properties": {k: v for k, v in row.items() if v is not None},
    }
    return LibraryToolDraft(
        client_item_id=str(row["geometry_id"]), name=name, data=data,
        asserts=asserts, presets=presets,
        source_format=SOURCE_FORMAT, client_name=CLIENT_NAME)


def _presets(con, geo: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-material/per-machine cutting-data rows → preset contributions.

    Vectric scopes cutting data by (tool, material, machine). Raw feed and RPM
    never persist — they normalize to vc / fz / ratio (the PRESETS.md floor);
    a row that cannot be normalized honestly is left in the preserved source
    properties instead of being guessed."""
    rows = con.execute("""
        SELECT tool_entity.material_id, tool_entity.machine_id,
               tool_cutting_data.*
        FROM tool_entity
        INNER JOIN tool_cutting_data
        ON tool_cutting_data.id = tool_entity.tool_cutting_data_id
        WHERE tool_entity.tool_geometry_id = ?
          AND tool_entity.material_id IS NOT NULL
    """, (geo["geometry_id"],)).fetchall()

    out: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    for r in rows:
        r = dict(r)
        material = _lookup_name(con, "material", r.get("material_id"))
        if not material:
            continue                    # no material statement — below the floor
        body = _translate(r, geo, material,
                          _lookup_name(con, "machine", r.get("machine_id")))
        if body is None:
            continue
        # Two rows may share material+machine (e.g. profile vs clear rates
        # split); disambiguate the (origin, label) identity deterministically.
        label = body["label"]
        if label in seen:
            seen[label] += 1
            body["label"] = f"{label} [{seen[label]}]"
        else:
            seen[label] = 1
        out.append(body)
    return out


def _translate(r: Dict[str, Any], geo: Dict[str, Any], material: str,
               machine: Optional[str]) -> Optional[Dict[str, Any]]:
    rate_factor = _RATE_TO_MM_MIN.get(r.get("rate_units"))
    n = _num(r.get("spindle_speed"))
    feed = _num(r.get("feed_rate"))
    plunge = _num(r.get("plunge_rate"))
    dia_mm = _num(geo.get("diameter"))
    if dia_mm is not None:
        dia_mm *= _TO_MM.get(geo.get("units"), 1.0)
    flutes = _num(geo.get("num_flutes"))

    body: Dict[str, Any] = {
        "origin": ORIGIN,
        "label": f"{material} @ {machine}" if machine else material,
        "material": {"name": material},
    }
    if n and dia_mm:
        body["vc"] = {"value": round(math.pi * dia_mm * n / 1000.0, 2),
                      "unit": "m/min"}
    if n and feed is not None and rate_factor and flutes:
        body["fz"] = {"value": round(feed * rate_factor / (n * flutes), 4),
                      "unit": "mm"}
    if feed and plunge is not None:
        body["ratio"] = {"value": round(plunge / feed, 4)}
    if not any(k in body for k in ("vc", "fz", "ratio")):
        return None                     # no engineering values — floor not met

    lu = _LEN_UNITS.get(r.get("length_units"))
    extras = {}
    for col in ("stepdown", "stepover", "clear_stepover"):
        val = _num(r.get(col))
        if val is not None and lu:
            extras[col] = {"value": val, "unit": lu}
    if r.get("tool_number") is not None:
        extras["tool_number"] = {"value": r["tool_number"]}
    if extras:
        body["extras"] = extras
    return body


def _lookup_name(con, table: str, row_id) -> Optional[str]:
    if not row_id:
        return None
    try:
        row = con.execute(f"SELECT name FROM {table} WHERE id = ?",  # noqa: S608
                          (row_id,)).fetchone()
    except sqlite3.Error:
        return None
    return row["name"] if row and row["name"] else None


def _num(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# -- {Tool Type} name templates ----------------------------------------------
# tool_geometry.name_format is usually a literal name, but may carry Vectric's
# documented template variables ({Diameter|F} = fractional-inch, {X|0.0} =
# decimal pattern). Unknown variables are left in place, never invented.

def _expand_name_format(fmt: str, row: Dict[str, Any]) -> str:
    if "{" not in fmt:
        return fmt.strip()
    unit_idx = row.get("units")
    values = {
        "tool type": TOOL_TYPES.get(row.get("tool_type")),
        "units short": _LEN_UNITS.get(unit_idx),
        "diameter": row.get("diameter"),
        "included angle": row.get("included_angle"),
        "side angle": (row.get("included_angle") / 2.0
                       if isinstance(row.get("included_angle"), (int, float))
                       else None),
        "tip radius": row.get("tip_radius"),
        "num flutes": row.get("num_flutes"),
        "tool number": row.get("tool_number"),
    }

    out, i = [], 0
    while i < len(fmt):
        if fmt[i] != "{":
            out.append(fmt[i])
            i += 1
            continue
        end = fmt.find("}", i)
        if end < 0:
            out.append(fmt[i:])
            break
        token = fmt[i + 1:end]
        key, _, spec = token.partition("|")
        val = values.get(key.strip().lower())
        if val is None:
            out.append(fmt[i:end + 1])          # unknown — leave verbatim
        else:
            out.append(_format_value(val, spec, unit_idx))
        i = end + 1
    return "".join(out).strip()


def _format_value(val, spec: str, unit_idx) -> str:
    if not isinstance(val, (int, float)):
        return str(val)
    if spec == "F" and unit_idx == 1:           # fractional inches
        frac = Fraction(val).limit_denominator(64)
        whole, rem = divmod(frac.numerator, frac.denominator)
        if rem == 0:
            return str(whole)
        part = f"{rem}/{frac.denominator}"
        return f"{whole} {part}" if whole else part
    if spec and "." in spec:                    # e.g. 0.0 / 0.00 decimal pattern
        return f"{val:.{len(spec.split('.')[1])}f}"
    return f"{val:g}"
