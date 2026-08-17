# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Drive an importer's drafts into a Loobric server through the public API.

Each draft becomes a ``ToolCatalogRecord`` via ``create_catalog_record`` — the
server stamps ``asserted:<source>`` on every canonical field; the client never
writes provenance. The full source payload is then preserved verbatim in the
record's own client section (the sync door), so the import is lossless and the
unmapped source codes survive for later promotion. Re-importing the same catalog
hits the server's natural-key ``409`` and is reported as *skipped*, never
duplicated.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from loobric.errors import HTTPError, LoobricClientError


@dataclass
class ImportReport:
    """The outcome of an import run, partitioned so a caller (CLI or tests) can
    report precisely what happened to each draft."""

    created: List[Tuple[Any, dict]] = field(default_factory=list)
    skipped: List[Tuple[Any, str]] = field(default_factory=list)
    failed: List[Tuple[Any, Exception]] = field(default_factory=list)
    # Created, but storing the raw payload afterward failed — the canonical
    # record exists; only the lossless copy is missing. Surfaced, not swallowed.
    preserve_failed: List[Tuple[Any, Exception]] = field(default_factory=list)
    media_uploaded: int = 0
    media_failed: List[Tuple[Any, Any, Exception]] = field(default_factory=list)


def import_drafts(client, drafts, *, source: Optional[str] = None,
                  client_name: Optional[str] = None, preserve: bool = True,
                  on_event: Optional[Callable[[str, Any, Any], None]] = None) -> ImportReport:
    """Create a catalog record per draft, preserve its raw payload, and upload its
    media. ``source``/``client_name`` override the per-draft defaults when given.
    ``on_event(kind, draft, info)`` reports progress (kinds: ``create``/``skip``/
    ``fail``/``preserve_fail``/``media``/``media_fail``)."""
    report = ImportReport()
    for draft in drafts:
        missing = draft.missing_identity()
        if missing:
            reason = "missing identity: " + ", ".join(missing)
            report.skipped.append((draft, reason))
            _emit(on_event, "skip", draft, reason)
            continue

        actor = source or draft.source_actor
        cname = client_name or draft.client_name
        try:
            rec = client.create_catalog_record(source=actor, fields=draft.fields)
        except HTTPError as e:
            if e.status == 409:                      # natural-key duplicate (M2)
                report.skipped.append((draft, "already exists (natural-key 409)"))
                _emit(on_event, "skip", draft, "already exists")
            else:
                report.failed.append((draft, e))
                _emit(on_event, "fail", draft, e)
            continue
        except LoobricClientError as e:
            report.failed.append((draft, e))
            _emit(on_event, "fail", draft, e)
            continue

        rid = (rec.get("internal") or {}).get("id")
        report.created.append((draft, rec))
        _emit(on_event, "create", draft, rid)
        if rid is None:
            continue

        if preserve:
            try:
                client.sync_client_section(
                    "tool-catalog-records", rid, cname,
                    data={"format": draft.source_format,
                          "class": draft.source_class,
                          "properties": draft.raw})
            except LoobricClientError as e:
                report.preserve_failed.append((draft, e))
                _emit(on_event, "preserve_fail", draft, e)

        for mf in draft.media:
            try:
                client.upload_media("tool-catalog-records", rid, data=mf.data,
                                    filename=mf.filename, role=mf.role,
                                    content_type=mf.content_type, actor=actor)
            except LoobricClientError as e:
                report.media_failed.append((draft, mf, e))
                _emit(on_event, "media_fail", draft, mf)
            else:
                report.media_uploaded += 1
                _emit(on_event, "media", draft, mf)

    return report


def _emit(cb, kind, draft, info):
    if cb is not None:
        cb(kind, draft, info)


@dataclass
class LibraryImportReport:
    """Outcome of a CAM-library import through the batch sync door, in the
    door's own result vocabulary (docs/BATCH_SYNC.md §2)."""

    created: List[Tuple[Any, dict]] = field(default_factory=list)
    updated: List[Tuple[Any, dict]] = field(default_factory=list)
    unchanged: List[Tuple[Any, dict]] = field(default_factory=list)
    failed: List[Tuple[Any, Any]] = field(default_factory=list)
    presets_contributed: int = 0
    presets_skipped: int = 0
    asserts_blocked: int = 0


def import_library_drafts(client, drafts, *, client_name: Optional[str] = None,
                          client_version: str = "",
                          on_event: Optional[Callable[[str, Any, Any], None]] = None
                          ) -> LibraryImportReport:
    """Upsert CAM-library tools as ToolInstanceRecords via the batch sync door
    (server >= 0.15.0). Identity is ``(client, client_item_id)``, so re-running
    the same import updates records in place instead of duplicating. Asserts and
    preset contributions ride the same batch items; the server stamps all
    provenance. Event kinds: ``created``/``updated``/``unchanged``/``fail``."""
    report = LibraryImportReport()
    if not drafts:
        return report

    cname = client_name or drafts[0].client_name
    items = []
    for d in drafts:
        item = {"client_item_id": d.client_item_id, "data": d.data,
                "asserts": [
                    dict({"path": path, "value": value},
                         **({"unit": unit} if unit else {}))
                    for path, value, unit in d.asserts]}
        if d.presets:
            item["presets"] = d.presets
        items.append(item)

    try:
        results = client.sync_tool_records(cname, items,
                                           client_version=client_version)
    except HTTPError as e:
        if e.status == 404:
            raise LoobricClientError(
                "the server has no batch sync door (needs loobric-server "
                ">= 0.15.0) — CAM library import requires it") from e
        raise

    for draft, res in zip(drafts, results):
        outcome = res.get("result")
        if outcome not in ("created", "updated", "unchanged"):
            report.failed.append((draft, res.get("error") or outcome))
            _emit(on_event, "fail", draft, res.get("error") or outcome)
            continue
        getattr(report, outcome).append((draft, res))
        report.presets_contributed += res.get("presets_contributed", 0)
        report.presets_skipped += res.get("presets_skipped", 0)
        report.asserts_blocked += res.get("asserts_blocked", 0)
        _emit(on_event, outcome, draft, res.get("id"))
    return report
