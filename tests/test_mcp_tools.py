# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Tests for the SDK-independent MCP tool registry (loobric.mcp.tools).

The registry encodes the locked MCP_PLAN.md decisions:
- writes declare the agent actor `<agent>@mcp` (LOOBRIC_MCP_AGENT, default "agent")
- agents assert, never observe: no observe-door tool exists
- no deletes, no Inbox confirmation, no bind/unbind, no credential management
- the observed guard: asserting over a field whose current source is
  `observed` is refused client-side before the request is made
- tool names/descriptions speak the public vocabulary (rejected glossary
  terms never appear)

Assumptions:
- Handlers are plain functions taking (client, arguments) so they test
  against a fake Client without the MCP SDK installed
"""
import json

import pytest

import loobric.mcp.tools as mcp_tools


class FakeClient:
    """Records calls; returns canned record shapes."""

    def __init__(self, canonical=None):
        self.calls = []
        self._canonical = canonical or {}

    def _record(self):
        return {"internal": {"id": "rec1"}, "canonical": self._canonical,
                "clients": {}}

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name.startswith("list_"):
                return []
            return self._record()
        return method


# -- registry shape ----------------------------------------------------------

def test_registry_is_complete_and_unique():
    names = [t.name for t in mcp_tools.TOOLS]
    assert len(names) == len(set(names))
    for tool in mcp_tools.TOOLS:
        assert tool.name and tool.name == tool.name.lower()
        assert tool.description
        assert tool.input_schema["type"] == "object"
        assert callable(tool.handler)


def test_no_gated_or_destructive_tools():
    """The locked exclusions: deletes, Inbox confirmation, bind/unbind,
    the observe door, and credential management never appear."""
    forbidden = ("delete", "confirm", "reject", "bind", "unbind", "observe",
                 "register", "login", "logout", "key", "user_create", "wipe",
                 "reset", "seed")
    # Token-boundary matching (underscores are separators): the ratified
    # "preset" (PRESETS.md) is not a "reset" tool, but a hypothetical
    # "delete_preset" still trips.
    import re
    for tool in mcp_tools.TOOLS:
        name = tool.name.replace("_", " ")
        for word in forbidden:
            pattern = r"\b%s\b" % re.escape(word.replace("_", " "))
            assert not re.search(pattern, name), (tool.name, word)


def test_vocabulary_denylist():
    """Rejected/removed glossary terms (UBIQUITOUS_LANGUAGE reboot R2) and
    client-side-only words must not reach the agent-facing surface."""
    denied = ("adopt", "coverage", "reconcile", "needs attention", "mirror",
              "slot", "mint", "library")
    # Word-boundary matching: the ratified op_type "slotting" (PRESETS.md)
    # is not the rejected tool-table "slot".
    import re
    for tool in mcp_tools.TOOLS:
        surface = (tool.name + " " + tool.description).lower()
        for word in denied:
            assert not re.search(r"\b%s\b" % re.escape(word), surface), \
                (tool.name, word)


# -- the agent actor ---------------------------------------------------------

def test_agent_actor_default(monkeypatch):
    monkeypatch.delenv("LOOBRIC_MCP_AGENT", raising=False)
    assert mcp_tools.agent_actor() == "agent@mcp"


def test_agent_actor_from_env(monkeypatch):
    monkeypatch.setenv("LOOBRIC_MCP_AGENT", "claude")
    assert mcp_tools.agent_actor() == "claude@mcp"


# -- read dispatch -----------------------------------------------------------

def test_read_tools_dispatch_to_client():
    client = FakeClient()
    mcp_tools.call_tool(client, "list_machines", {})
    mcp_tools.call_tool(client, "list_tool_instance_records", {})
    mcp_tools.call_tool(client, "get_tool_set", {"record_id": "abc"})
    called = [name for name, _, _ in client.calls]
    assert "list_machines" in called
    assert "list_tool_records" in called
    assert "get_tool_set" in called


def test_query_audit_logs_dispatch():
    client = FakeClient()
    mcp_tools.call_tool(client, "query_audit_logs",
                        {"entity_type": "tool_instance_record"})
    name, args, kwargs = client.calls[0]
    assert name == "query_audit_logs"
    assert kwargs.get("entity_type") == "tool_instance_record"


# -- writes carry the agent actor -------------------------------------------

def test_contribute_preset_stamps_agent_actor(monkeypatch):
    monkeypatch.setenv("LOOBRIC_MCP_AGENT", "claude")
    client = FakeClient()
    mcp_tools.call_tool(client, "contribute_preset", {
        "resource": "tool-catalog-records", "record_id": "r1",
        "origin": "manufacturer", "label": "6061 profiling",
        "material": {"name": "6061-T6"},
        "vc": {"value": 250, "unit": "m/min"}})
    name, args, kwargs = client.calls[0]
    assert name == "contribute_preset"
    assert args[:2] == ("tool-catalog-records", "r1")
    assert kwargs.get("actor") == "claude@mcp"


def test_contribute_preset_description_teaches_the_doctrine():
    """The description is the agent's only manual: it must teach that a
    preset is a recommendation with a source, that raw feed/RPM are never
    stored, the origin-vs-transcriber split (no laundering AI numbers as the
    manufacturer's), and that replace-own is the only revision path."""
    tool = next(t for t in mcp_tools.TOOLS if t.name == "contribute_preset")
    surface = tool.description
    assert "RECOMMENDATION WITH A SOURCE" in surface
    assert "NEVER stored" in surface
    assert "launder" in surface
    assert "replaces" in surface


def test_create_catalog_record_stamps_agent_actor(monkeypatch):
    monkeypatch.setenv("LOOBRIC_MCP_AGENT", "claude")
    client = FakeClient()
    mcp_tools.call_tool(client, "create_catalog_record", {
        "fields": {"name": {"value": "6mm endmill"},
                   "manufacturer": {"value": "shop"},
                   "product_code": {"value": "EM-6"}}})
    name, args, kwargs = client.calls[0]
    assert name == "create_catalog_record"
    assert kwargs.get("source") == "claude@mcp"


def test_create_catalog_record_description_teaches_field_placement():
    """The first real-world session (2026-07-25) sent spec fields at the top
    level (flute_count, hand_of_cut), got rejected by the server's
    extra='forbid' lane discipline, and crammed the data into the name string.
    The description is the agent's only manual: it must teach the nested
    `geometry` object, the canonical key names (`flutes`, not flute_count),
    and that non-geometry manufacturer data belongs in `client_data` —
    stored, not discarded."""
    tool = next(t for t in mcp_tools.TOOLS
                if t.name == "create_catalog_record")
    # The agent sees both the description and the input schema — check the
    # combined surface.
    surface = tool.description + json.dumps(tool.input_schema)
    assert '\\"geometry\\"' in surface   # nesting shown in the JSON example
    assert "flutes" in surface           # the canonical key name
    assert "client_data" in surface      # the home for non-geometry extras
    assert "never invent" in surface     # honest-sparse survives the rewrite


def test_create_catalog_record_names_the_client_for_client_data():
    """The server stores `client_data` only when a `client` name accompanies
    it — otherwise it is silently dropped (found by the media e2e smoke). If
    the agent sends client_data without naming a client, the handler must
    inject client='mcp' so preserved manufacturer data actually persists."""
    client = FakeClient()
    mcp_tools.call_tool(client, "create_catalog_record", {
        "fields": {"name": {"value": "em"},
                   "manufacturer": {"value": "shop"},
                   "product_code": {"value": "EM-1"},
                   "client_data": {"grade": "KCPM15"}}})
    _, _, kwargs = client.calls[0]
    assert kwargs["fields"]["client"] == "mcp"
    # an explicitly named client is left alone
    client2 = FakeClient()
    mcp_tools.call_tool(client2, "create_catalog_record", {
        "fields": {"name": {"value": "em"},
                   "client": "freecad",
                   "client_data": {"x": 1}}})
    _, _, kwargs2 = client2.calls[0]
    assert kwargs2["fields"]["client"] == "freecad"


# -- media: attach from URL --------------------------------------------------

def test_attach_media_downloads_and_uploads(monkeypatch):
    """The tool downloads the URL and pushes the bytes through the client's
    audited media door with the agent actor; the filename defaults to the
    URL's basename."""
    monkeypatch.setenv("LOOBRIC_MCP_AGENT", "claude")
    monkeypatch.setattr(mcp_tools, "_download_media",
                        lambda url: (b"solid model bytes", "model/step"))
    client = FakeClient()
    mcp_tools.call_tool(client, "attach_media_from_url", {
        "resource": "tool-catalog-records", "record_id": "rec1",
        "url": "https://example.com/cad/H1TE4SE0250.stp",
        "role": "model_3d"})
    name, args, kwargs = client.calls[0]
    assert name == "upload_media"
    assert args == ("tool-catalog-records", "rec1")
    assert kwargs["data"] == b"solid model bytes"
    assert kwargs["filename"] == "H1TE4SE0250.stp"
    assert kwargs["role"] == "model_3d"
    assert kwargs["content_type"] == "model/step"
    assert kwargs["actor"] == "claude@mcp"


def test_attach_media_explicit_filename_and_content_type(monkeypatch):
    monkeypatch.setattr(mcp_tools, "_download_media",
                        lambda url: (b"png bytes", "application/octet-stream"))
    client = FakeClient()
    mcp_tools.call_tool(client, "attach_media_from_url", {
        "resource": "tool-instance-records", "record_id": "rec1",
        "url": "https://example.com/dl?id=42", "role": "image",
        "filename": "photo.png", "content_type": "image/png"})
    _, _, kwargs = client.calls[0]
    assert kwargs["filename"] == "photo.png"
    assert kwargs["content_type"] == "image/png"


def test_attach_media_rejects_non_http_url():
    """Only http(s) sources: a file:// or ftp:// URL is refused before any
    fetch happens (the MCP server must never read local files into records)."""
    client = FakeClient()
    for url in ("file:///etc/passwd", "ftp://example.com/f.stp"):
        with pytest.raises(mcp_tools.MediaDownloadError):
            mcp_tools.call_tool(client, "attach_media_from_url", {
                "resource": "tool-catalog-records", "record_id": "rec1",
                "url": url, "role": "model_3d"})
    assert client.calls == []               # nothing reached the client


def test_attach_media_enforces_size_cap(monkeypatch):
    class FakeResponse:
        headers = type("H", (), {"get_content_type":
                                 staticmethod(lambda: "model/step")})()

        def read(self, n=-1):
            return b"x" * n                 # always fills the cap + 1 probe

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mcp_tools, "urlopen",
                        lambda req, timeout=None: FakeResponse())
    with pytest.raises(mcp_tools.MediaDownloadError):
        mcp_tools._download_media("https://example.com/huge.stp")


def test_attach_media_sends_loobric_user_agent(monkeypatch):
    """The fetch carries the transport's User-Agent (rebranded loobric-mcp/…
    by main) — default Python UAs get Cloudflare-403'd (error 1010)."""
    seen = {}

    class FakeResponse:
        headers = type("H", (), {"get_content_type":
                                 staticmethod(lambda: "image/png")})()

        def read(self, n=-1):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        return FakeResponse()

    monkeypatch.setattr(mcp_tools, "urlopen", fake_urlopen)
    data, ctype = mcp_tools._download_media("https://example.com/p.png")
    assert data == b"ok" and ctype == "image/png"
    from loobric import transport
    assert seen["ua"] == transport.USER_AGENT


def test_assert_field_uses_agent_actor(monkeypatch):
    monkeypatch.setenv("LOOBRIC_MCP_AGENT", "claude")
    client = FakeClient(canonical={
        "name": {"value": "old", "source": "asserted:human@cli"}})
    mcp_tools.call_tool(client, "assert_field", {
        "resource": "tool-instance-records", "record_id": "rec1",
        "path": "name", "value": "new"})
    assert_calls = [c for c in client.calls if c[0] == "assert_field"]
    assert len(assert_calls) == 1
    _, args, kwargs = assert_calls[0]
    assert kwargs.get("actor") == "claude@mcp"


# -- the observed guard ------------------------------------------------------

def test_assert_field_refuses_observed_value():
    client = FakeClient(canonical={
        "geometry": {"diameter": {"value": 6.35,
                                  "source": "observed:linuxcnc@mill01"}}})
    with pytest.raises(mcp_tools.ObservedValueError):
        mcp_tools.call_tool(client, "assert_field", {
            "resource": "tool-instance-records", "record_id": "rec1",
            "path": "geometry.diameter", "value": 6.0})
    assert not [c for c in client.calls if c[0] == "assert_field"]


def test_assert_field_allows_unknown_and_asserted():
    client = FakeClient(canonical={
        "name": {"value": None, "source": "unknown"}})
    mcp_tools.call_tool(client, "assert_field", {
        "resource": "tool-instance-records", "record_id": "rec1",
        "path": "name", "value": "roughing endmill"})
    assert [c for c in client.calls if c[0] == "assert_field"]


def test_assert_field_allows_field_with_no_current_value():
    client = FakeClient(canonical={})
    mcp_tools.call_tool(client, "assert_field", {
        "resource": "tool-instance-records", "record_id": "rec1",
        "path": "name", "value": "fresh"})
    assert [c for c in client.calls if c[0] == "assert_field"]
