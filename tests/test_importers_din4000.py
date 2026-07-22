# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""DIN 4000 importer tests.

Built around three real Kennametal exports of the same tool (article 6767731, a
1/16" 4-flute endmill) in CSV, ToolsUnited XML 2013, and XML 2016. The headline
invariant: all three parse to the *identical* canonical fields, even though the
2016 XML uses a decimal comma and a different Main-Data block.
"""
from pathlib import Path

import pytest

from loobric.errors import HTTPError
from loobric.importers import din4000
from loobric.importers.base import CatalogRecordDraft
from loobric.importers.run import import_drafts

FIXTURES = Path(__file__).parent / "fixtures" / "importers"
CSV = FIXTURES / "din4000-82.csv"
XML_2013 = FIXTURES / "din4000-82_2013.xml"
XML_2016 = FIXTURES / "din4000-82_2016.xml"

# The canonical fields every variant of article 6767731 must yield.
EXPECTED_FIELDS = {
    "name": {"value": "ENDMILL H1TE 1/16X1/8X1/8X1 1/2 S"},
    "manufacturer": {"value": "KH"},
    "product_code": {"value": "H1TE4SE0063R013HA_KCPM15"},
    "geometry": {
        "diameter": {"value": 1.588, "unit": "mm"},
        "shank_diameter": {"value": 3.175, "unit": "mm"},
        "length": {"value": 38.1, "unit": "mm"},
        "flutes": {"value": 4},
        "shape": {"value": "endmill"},
    },
}


@pytest.mark.parametrize("path", [CSV, XML_2013, XML_2016])
def test_parses_one_endmill(path):
    drafts = din4000.parse(path)
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.source_class == "DIN4000-82"
    assert draft.fields == EXPECTED_FIELDS


def test_all_three_variants_agree_on_canonical_fields():
    """CSV, XML 2013, and XML 2016 differ on the wire (decimal comma, Main-Data,
    extra codes) but must produce byte-identical canonical fields."""
    csv_fields = din4000.parse(CSV)[0].fields
    xml13_fields = din4000.parse(XML_2013)[0].fields
    xml16_fields = din4000.parse(XML_2016)[0].fields
    assert csv_fields == xml13_fields == xml16_fields == EXPECTED_FIELDS


def test_decimal_comma_in_2016_xml():
    """The 2016 XML writes 1,588 / 38,1 — must parse to the same floats as the
    decimal-point CSV, and must not corrupt the comma-list J8 field."""
    draft = din4000.parse(XML_2016)[0]
    assert draft.fields["geometry"]["diameter"]["value"] == 1.588
    assert draft.fields["geometry"]["length"]["value"] == 38.1
    # J8 is a comma-separated list, not a number — preserved verbatim, not mangled.
    assert draft.raw["J8"] == "FZI,FZI,FSE,FNU,FNU,FEC,FEC,FSE"


def test_raw_payload_preserved_losslessly():
    """Every source code survives on the draft, including the ones we don't map —
    so nothing is lost and unmapped codes can be promoted later."""
    draft = din4000.parse(CSV)[0]
    for code in ("A1", "B2", "B3", "C4", "D7", "F4", "H5", "J8", "NSM"):
        assert code in draft.raw, f"{code} missing from preserved raw payload"
    assert draft.raw["H5"] == "AlTiN"
    assert draft.raw["NSM"] == "DIN4000-82"


def test_endmill_guard_no_inference_beyond_mapped_codes():
    """The cardinal rule: we assert only what the source states. shape=endmill is
    allowed *because the source declares the class* (NSM=DIN4000-82) — but no
    unmapped code leaks into canonical geometry as a guessed field."""
    geom = din4000.parse(CSV)[0].fields["geometry"]
    # Exactly the mapped geometry keys — nothing inferred from B2/B3/C4/F4/etc.
    assert set(geom) == {"diameter", "shank_diameter", "length", "flutes", "shape"}


def test_unknown_class_asserts_nothing():
    """A class with no verified mapping yields no canonical fields and no shape —
    the raw is still preserved, but we never guess. (The endmill bug, prevented.)"""
    from loobric.importers.din4000 import _codes
    fields = _codes.to_fields("DIN4000-99", {"A1": "5.0", "J23": "Mystery tool"})
    assert fields == {}


# -- the run driver ----------------------------------------------------------

class FakeClient:
    """Records the API calls the driver makes, so we test behavior without HTTP."""

    def __init__(self, raise_409=False):
        self.raise_409 = raise_409
        self.created = []
        self.synced = []
        self._n = 0

    def create_catalog_record(self, source, fields):
        if self.raise_409:
            raise HTTPError(409, "natural key exists")
        self._n += 1
        self.created.append({"source": source, "fields": fields})
        return {"internal": {"id": f"cat{self._n}"}, "canonical": {}, "clients": {}}

    def sync_client_section(self, resource, record_id, client, data):
        self.synced.append({"resource": resource, "record_id": record_id,
                            "client": client, "data": data})
        return {}


def test_driver_creates_and_preserves():
    drafts = din4000.parse(CSV)
    client = FakeClient()
    report = import_drafts(client, drafts, source="din4000-import",
                           client_name="import:din4000")
    assert len(report.created) == 1 and not report.failed and not report.skipped
    # Created via the catalog door with the canonical fields; provenance is the
    # server's job, so the client sends none.
    assert client.created[0]["source"] == "din4000-import"
    assert client.created[0]["fields"] == EXPECTED_FIELDS
    # Raw preserved verbatim in the record's own client section.
    assert len(client.synced) == 1
    synced = client.synced[0]
    assert synced["resource"] == "tool-catalog-records"
    assert synced["client"] == "import:din4000"
    assert synced["data"]["properties"]["H5"] == "AlTiN"
    assert synced["data"]["class"] == "DIN4000-82"


def test_driver_no_preserve_skips_sync():
    client = FakeClient()
    import_drafts(client, din4000.parse(CSV), preserve=False)
    assert client.created and client.synced == []


def test_driver_reports_409_as_skipped_not_failed():
    """Re-importing a catalog that already exists hits the natural-key 409 and is
    reported as skipped — never duplicated, never a hard failure."""
    client = FakeClient(raise_409=True)
    report = import_drafts(client, din4000.parse(CSV))
    assert not report.created and not report.failed
    assert len(report.skipped) == 1
    assert "exists" in report.skipped[0][1]


def test_driver_skips_draft_missing_identity():
    """A draft lacking the identity floor (no product_code) is skipped before any
    API call — we don't send malformed records."""
    bad = CatalogRecordDraft(
        fields={"name": {"value": "x"}, "manufacturer": {"value": "KH"}},
        raw={}, source_format="din4000-csv", source_class="DIN4000-82")
    client = FakeClient()
    report = import_drafts(client, [bad])
    assert not client.created
    assert len(report.skipped) == 1 and "product_code" in report.skipped[0][1]
