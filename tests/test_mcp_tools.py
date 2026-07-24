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
    for tool in mcp_tools.TOOLS:
        for word in forbidden:
            assert word not in tool.name, (tool.name, word)


def test_vocabulary_denylist():
    """Rejected/removed glossary terms (UBIQUITOUS_LANGUAGE reboot R2) and
    client-side-only words must not reach the agent-facing surface."""
    denied = ("adopt", "coverage", "reconcile", "needs attention", "mirror",
              "slot", "mint", "library")
    for tool in mcp_tools.TOOLS:
        surface = (tool.name + " " + tool.description).lower()
        for word in denied:
            assert word not in surface, (tool.name, word)


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
