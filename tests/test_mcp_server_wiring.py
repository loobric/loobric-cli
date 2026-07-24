# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Smoke tests for the MCP SDK wiring (loobric.mcp.main).

Skipped when the optional `mcp` extra is not installed — the registry logic
itself is covered SDK-free in test_mcp_tools.py.

Assumptions:
- build_server() registers list/call tool handlers and the two resources
- Tool listing mirrors the registry exactly
"""
import pytest

pytest.importorskip("mcp")

import anyio
import mcp.types as types

from loobric.mcp.main import build_server
import loobric.mcp.tools as mcp_tools
import loobric.mcp.resources as mcp_resources


class _NullClient:
    pass


def test_build_server_registers_handlers():
    server = build_server(_NullClient())
    assert types.ListToolsRequest in server.request_handlers
    assert types.CallToolRequest in server.request_handlers
    assert types.ListResourcesRequest in server.request_handlers
    assert types.ReadResourceRequest in server.request_handlers
    # No parameterized resources exist, but hosts (e.g. the MCP Inspector)
    # probe this method — it must answer [] rather than -32601.
    assert types.ListResourceTemplatesRequest in server.request_handlers


def test_resource_templates_answers_empty():
    server = build_server(_NullClient())
    handler = server.request_handlers[types.ListResourceTemplatesRequest]
    result = anyio.run(handler, types.ListResourceTemplatesRequest(
        method="resources/templates/list"))
    assert result.root.resourceTemplates == []


def test_tool_listing_mirrors_registry():
    server = build_server(_NullClient())
    handler = server.request_handlers[types.ListToolsRequest]

    result = anyio.run(handler, types.ListToolsRequest(method="tools/list"))
    listed = {t.name for t in result.root.tools}
    assert listed == {t.name for t in mcp_tools.TOOLS}


def test_resources_present():
    assert {r["name"] for r in mcp_resources.RESOURCES} == {"glossary", "concepts"}
    for resource in mcp_resources.RESOURCES:
        assert resource["text"].strip()
        assert resource["uri"].startswith("loobric://")
