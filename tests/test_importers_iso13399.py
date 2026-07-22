# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""GTC / ISO 13399 / P21 importer tests.

P21 carries identity and geometry in readable entities and ISO 13399 mnemonics
(no PLIB dictionary needed). A GTC package wraps a P21 with 3D models and images,
which become canonical media. Fixtures are synthetic — no vendor catalogs.
"""
import io
import zipfile
from pathlib import Path

import pytest

from loobric import importers
from loobric.errors import HTTPError
from loobric.importers import gtc, p21
from loobric.importers.run import import_drafts

FIXTURES = Path(__file__).parent / "fixtures" / "importers"
P21_TEXT = (FIXTURES / "iso13399.p21").read_text()

FAKE_STP = b"ISO-10303-21;\nHEADER;\n/* a 3D model, not parsed */\nENDSEC;\nEND-ISO-10303-21;\n"
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

ASSORTMENT = b"""<?xml version="1.0" encoding="utf-8"?>
<package_assortment>
  <item>
    <product_id>6676918</product_id>
    <gtc_generic_class_id>MILSQS</gtc_generic_class_id>
    <p21_file_name>KH_6676918.p21</p21_file_name>
    <unit_system>metric</unit_system>
  </item>
</package_assortment>"""


# -- P21 ----------------------------------------------------------------------

def test_p21_extracts_identity_and_geometry():
    draft = p21.parse(FIXTURES / "iso13399.p21")[0]
    assert draft.name == "END MILL HARVI I TE 1/4X1/4X3/4X2 1/2 S"
    assert draft.manufacturer == "Kennametal"
    assert draft.product_code == "H1TE4SE0250L075HA_KCPM15"
    assert draft.fields["item_type"] == {"value": "tool_item"}    # ISO role, read
    geom = draft.fields["geometry"]
    assert geom["diameter"] == {"value": 6.35, "unit": "mm"}        # DC
    assert geom["shank_diameter"] == {"value": 6.35, "unit": "mm"}  # DCONMS
    assert geom["length"] == {"value": 63.5, "unit": "mm"}          # OAL
    assert geom["cutting_edge_height"] == {"value": 19.05, "unit": "mm"}  # APMX
    assert geom["flutes"] == {"value": 4}                           # ZEFF (int)
    assert draft.raw["product_id"] == "6676918"
    assert draft.raw["mnemonics"]["FHA"] == "36"                    # unmapped, preserved


def test_p21_without_an_item_yields_nothing():
    """A plain geometry STEP file (no tool ITEM) parses to no drafts, not junk."""
    assert p21.parse_text("ISO-10303-21;\nDATA;\n#1=CARTESIAN_POINT('',(0.,0.));\nENDSEC;") is None


# -- GTC package --------------------------------------------------------------

def _gtc20_zip() -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("package_assortment.xml", ASSORTMENT)
        z.writestr("product_data_files/KH_6676918.p21", P21_TEXT)
        z.writestr("product_3d_models_detailed/6676918-KH-stp.stp", FAKE_STP)
        z.writestr("product_3d_models_basic/6676918-KH-stpbasic.stp", FAKE_STP)
        z.writestr("product_brand_logos/KH.png", FAKE_PNG)
        z.writestr("class_icons/ZYL.png", FAKE_PNG)        # class-level: must be skipped
    buf.seek(0)
    return buf


def test_gtc20_package_parses_with_shape_and_media(tmp_path):
    path = tmp_path / "6676918.zip"
    path.write_bytes(_gtc20_zip().read())
    draft = gtc.parse(path)[0]
    assert draft.name == "END MILL HARVI I TE 1/4X1/4X3/4X2 1/2 S"
    assert draft.source_class == "MILSQS"
    assert draft.fields["geometry"]["shape"] == {"value": "endmill"}   # class declares it
    assert draft.fields["geometry"]["diameter"] == {"value": 6.35, "unit": "mm"}
    roles = sorted(m.role for m in draft.media)
    assert roles == ["logo", "model_3d", "model_3d_basic"]             # class_icon skipped
    model = next(m for m in draft.media if m.role == "model_3d")
    assert model.content_type == "model/step" and model.data == FAKE_STP


def test_gtc17_nested_inner_zips_are_unwrapped(tmp_path):
    """GTC 2017 inner-zips each file; the reader unwraps them transparently."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in [("KH_6676918.p21", P21_TEXT.encode()),
                           ("6676918-KH-stp.stp", FAKE_STP)]:
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w") as iz:
                iz.writestr(name, data)
            z.writestr("Documents/Brands/TU/%s.zip" % name, inner.getvalue())
    path = tmp_path / "6676918_gtc17.zip"
    path.write_bytes(buf.getvalue())
    draft = gtc.parse(path)[0]
    assert draft.product_code == "H1TE4SE0250L075HA_KCPM15"
    assert any(m.role == "model_3d" for m in draft.media)


# -- dispatcher ---------------------------------------------------------------

def test_dispatch_by_format(tmp_path):
    assert importers.parse(FIXTURES / "iso13399.p21")[0].source_format == "p21"
    assert importers.parse(FIXTURES / "din4000-82.csv")[0].source_format == "din4000-csv"
    gz = tmp_path / "p.zip"
    gz.write_bytes(_gtc20_zip().read())
    assert importers.parse(gz)[0].source_format == "gtc"


# -- run driver: media upload -------------------------------------------------

class FakeClient:
    def __init__(self):
        self.created, self.synced, self.media = [], [], []
        self._n = 0

    def create_catalog_record(self, source, fields):
        self._n += 1
        self.created.append({"source": source, "fields": fields})
        return {"internal": {"id": f"cat{self._n}"}}

    def sync_client_section(self, resource, record_id, client, data):
        self.synced.append((resource, record_id, client))
        return {}

    def upload_media(self, resource, record_id, *, data, filename, role,
                     content_type="application/octet-stream", actor=None):
        self.media.append({"resource": resource, "record_id": record_id,
                           "role": role, "filename": filename,
                           "content_type": content_type, "actor": actor})
        return {}


def test_driver_uploads_media_after_create(tmp_path):
    path = tmp_path / "p.zip"
    path.write_bytes(_gtc20_zip().read())
    drafts = gtc.parse(path)
    client = FakeClient()
    report = import_drafts(client, drafts)
    assert len(report.created) == 1
    # per-draft default actor used (gtc-import), since the CLI passed no override
    assert client.created[0]["source"] == "gtc-import"
    assert report.media_uploaded == 3 and len(client.media) == 3
    assert {m["role"] for m in client.media} == {"model_3d", "model_3d_basic", "logo"}
    assert all(m["record_id"] == "cat1" for m in client.media)
    assert all(m["actor"] == "gtc-import" for m in client.media)


def test_driver_media_failure_is_reported_not_fatal(tmp_path):
    path = tmp_path / "p.zip"
    path.write_bytes(_gtc20_zip().read())

    class Boom(FakeClient):
        def upload_media(self, *a, **k):
            raise HTTPError(500, "nope")

    report = import_drafts(Boom(), gtc.parse(path))
    assert len(report.created) == 1                  # record still created
    assert report.media_uploaded == 0
    assert len(report.media_failed) == 3


def test_client_upload_media_builds_multipart_post(monkeypatch):
    """The real Client.upload_media posts a well-formed multipart body to the
    record's media endpoint (FakeClient bypasses this construction)."""
    import loobric.transport as transport
    from loobric.client import Client

    seen = {}

    def fake(method, endpoint, **kw):
        seen.update(method=method, endpoint=endpoint, kw=kw)
        return {}

    monkeypatch.setattr(transport, "make_request", fake)
    Client(base_url="http://x").upload_media(
        "tool-catalog-records", "abc", data=b"hi", filename="m.stp",
        role="model_3d", content_type="model/step", actor="gtc-import")

    assert seen["method"] == "POST"
    assert seen["endpoint"] == "/tool-catalog-records/abc/media"
    assert seen["kw"]["content_type"].startswith("multipart/form-data; boundary=")
    body = seen["kw"]["raw_body"]
    assert b'name="role"' in body and b"model_3d" in body
    assert b'name="actor"' in body and b"gtc-import" in body
    assert b'filename="m.stp"' in body and b"model/step" in body and b"hi" in body
