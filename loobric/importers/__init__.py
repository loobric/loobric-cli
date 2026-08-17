# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Format importers: parse a vendor tool-data export into catalog records.

An importer is a *pure parse-and-map* step. It never opens a socket: it turns a
file into one or more :class:`CatalogRecordDraft` (canonical `fields` + the raw
source payload to preserve). The :mod:`loobric.importers.run` driver is
what pushes those drafts through the public API — so parsing is offline,
testable, and the network concern lives in exactly one place.

Importers create **ToolCatalogRecords only** (catalog *types*), with nominal
geometry the server stamps `asserted:<source>`. They never observe, never touch
instances or entries, and — critically — never *infer* a field the source did
not state. A code we cannot pin to a meaning is preserved verbatim, never
guessed (the "every imported tool became an endmill" failure the schema exists
to prevent).
"""
import re
from pathlib import Path
from typing import List, Union

from loobric.importers.base import (CatalogRecordDraft, LibraryToolDraft,
                                    MediaFile)

__all__ = ["CatalogRecordDraft", "LibraryToolDraft", "MediaFile", "parse"]

# XML root element -> importer module name. Lets one `.xml` extension fan out to
# the ToolsUnited DIN 4000, SolidCAM, and hyperMILL formats.
_XML_ROOTS = {
    "tool-data": "din4000",     # ToolsUnited DIN 4000
    "results": "solidcam",      # SolidCAM <Results><Tools><Tool>
    "omtdx": "hypermill",       # OPEN MIND hyperMILL
}


def parse(path: Union[str, Path]) -> List[CatalogRecordDraft]:
    """Detect the format from the file and dispatch to the right importer.

    - ``.zip`` (or a PK header) → GTC package (ISO 13399, with media)
    - ``.p21`` / ``.stp`` / ``.step`` / an ``ISO-10303-21`` header → STEP P21
    - XML → by root element: DIN 4000 / SolidCAM / hyperMILL
    - SQLite → by table set: Vectric ``.vtdb`` / SprutCam ``.db``
    - JSON → CAMotics tool table (a Fusion library JSON is rejected with a
      pointer to loobric-fusion)
    - ``.csv`` (or anything else) → DIN 4000
    """
    name = str(path).lower()
    head = Path(path).read_bytes()[:2048]
    if name.endswith(".zip") or head[:2] == b"PK":
        from loobric.importers import gtc
        return gtc.parse(path)
    if (name.endswith((".p21", ".stp", ".step"))
            or head.lstrip().startswith(b"ISO-10303-21")):
        from loobric.importers import p21
        return p21.parse(path)
    if head[:16] == b"SQLite format 3\x00":
        return _parse_sqlite(path)
    if name.endswith(".xml") or head.lstrip()[:1] == b"<":
        module = _XML_ROOTS.get(_xml_root_tag(head), "din4000")
        mod = __import__("loobric.importers." + module, fromlist=["parse"])
        return mod.parse(path)
    if name.endswith(".json") or head.lstrip()[:1] in (b"{", b"["):
        from loobric.importers import camotics
        return camotics.parse(path)
    from loobric.importers import din4000
    return din4000.parse(path)


def _parse_sqlite(path):
    """Tell the SQLite-based CAM libraries apart by their table sets."""
    import sqlite3
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
    finally:
        con.close()
    from loobric.importers import sprutcam, vectric
    if vectric.sniff(tables):
        return vectric.parse(path)
    if sprutcam.sniff(tables):
        return sprutcam.parse(path)
    raise ValueError(
        "unrecognized SQLite tool database (expected Vectric tool_geometry "
        "or SprutCam ISTMillToolAccessor tables)")


def _xml_root_tag(head: bytes) -> str:
    """The first element name (namespace/declaration/doctype stripped), lowercased."""
    text = head.decode("utf-8-sig", errors="replace")
    text = re.sub(r"<\?.*?\?>", "", text, flags=re.S)   # drop <?xml …?>
    text = re.sub(r"<!.*?>", "", text, flags=re.S)       # drop <!DOCTYPE …> / comments
    m = re.search(r"<([A-Za-z_][\w.\-]*)", text)
    return m.group(1).lower() if m else ""
