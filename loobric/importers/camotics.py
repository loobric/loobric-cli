# MIT License
# Copyright (c) 2026 sliptonic
# SPDX-License-Identifier: MIT
"""CAMotics tool-table reader (JSON).

CAMotics is open source, so this is the one CAM format read from documentation
rather than reverse-engineering: ``src/gcode/Tool.cpp`` writes each tool as
``{units, shape, length, diameter, snub_diameter?, description}``. A tool-table
export is an object keyed by tool number; a full ``.camotics`` project carries
the same object under ``"tools"``. Both are accepted.

Tool number is the only identity a CAMotics table has, so records key on it.
A Fusion 360 library JSON (``{"data": [...]}``) is rejected with a pointer to
loobric-fusion — wrong tool, not a guess.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Union

from loobric.importers.base import LibraryToolDraft

SOURCE_FORMAT = "camotics"
CLIENT_NAME = "camotics"

# CAMotics' declared shape -> canonical. Conical/Snubnose/Spheroid have no
# unambiguous match in the canonical vocabulary and stay unmapped (the declared
# string is preserved in the client section either way).
SHAPE_MAP = {"cylindrical": "endmill", "ballnose": "ballend"}

_UNITS = {"metric": "mm", "mm": "mm", "imperial": "in", "inch": "in"}


def parse(path: Union[str, Path]) -> List[LibraryToolDraft]:
    return parse_bytes(Path(path).read_bytes())


def parse_bytes(raw: bytes) -> List[LibraryToolDraft]:
    doc = json.loads(raw.decode("utf-8-sig"))
    if isinstance(doc, dict) and isinstance(doc.get("data"), list):
        raise ValueError(
            "this looks like a Fusion 360 tool library JSON — "
            "import it with the loobric-fusion client instead")
    if isinstance(doc, dict) and isinstance(doc.get("tools"), dict):
        doc = doc["tools"]              # a .camotics project file
    if not isinstance(doc, dict):
        raise ValueError("not a CAMotics tool table (expected a JSON object "
                         "keyed by tool number)")

    drafts = []
    for number, tool in sorted(doc.items(),
                               key=lambda kv: _num_key(kv[0])):
        if not isinstance(tool, dict) or _num_key(number) is None:
            continue
        drafts.append(_draft(int(number), tool))
    return drafts


def _draft(number: int, tool: Dict[str, Any]) -> LibraryToolDraft:
    unit = _UNITS.get(str(tool.get("units", "")).lower())
    name = (tool.get("description") or "").strip() \
        or f"T{number} {tool.get('shape', 'tool')}".strip()

    asserts = []
    if unit is not None:
        for key, path in (("diameter", "geometry.diameter"),
                          ("length", "geometry.length")):
            try:
                val = float(tool[key])
            except (KeyError, TypeError, ValueError):
                continue
            if val:
                asserts.append((path, val, unit))
    shape = SHAPE_MAP.get(str(tool.get("shape", "")).lower())
    if shape:
        asserts.append(("geometry.shape", shape, None))

    data = {"format": SOURCE_FORMAT, "tool_number": number,
            "properties": dict(tool)}
    return LibraryToolDraft(
        client_item_id=f"tool:{number}", name=name, data=data,
        asserts=asserts, source_format=SOURCE_FORMAT, client_name=CLIENT_NAME)


def _num_key(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
