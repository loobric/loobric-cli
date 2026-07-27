# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Entry point and MCP SDK wiring for the Loobric MCP server (stdio).

Configuration (environment):
- LOOBRIC_BASE_URL  — required; the Loobric Server to act on
- LOOBRIC_API_KEY   — API key; omit against a solo-mode server
- LOOBRIC_MCP_AGENT — the agent product name for provenance (default "agent")

The MCP SDK is the optional ``loobric-cli[mcp]`` extra; without it this
entry point exits with install instructions instead of a traceback.

Assumptions:
- stdio transport only (a hosted/remote MCP endpoint is a later, separate
  project — see MCP_PLAN.md §2)
- The transport User-Agent is rebranded loobric-mcp/<version> so Cloudflare
  allows it and server logs can tell the channels apart
"""
import json
import sys
from typing import Any


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("loobric-cli")
    except Exception:
        return "unknown"


def _client_from_env():
    import os
    from loobric import transport
    from loobric.client import Client

    base_url = os.getenv("LOOBRIC_BASE_URL")
    if not base_url:
        sys.exit("loobric-mcp: set LOOBRIC_BASE_URL to your Loobric Server "
                 "(and LOOBRIC_API_KEY unless it runs in solo mode).")
    transport.USER_AGENT = "loobric-mcp/" + _version()
    return Client(base_url=base_url, api_key=os.getenv("LOOBRIC_API_KEY"))


# The doors this MCP server actually uses. Anything beyond these on the
# configured key is unused power a raw-client bypass would inherit.
_MCP_DOORS = {"read", "sync", "assert"}


def scope_warning(me: dict) -> "str | None":
    """A least-privilege warning when the configured key grants doors the MCP
    server never uses (SCOPES_PLAN Q12: warn, don't refuse).

    `me` is the /auth/me response; a 0.6.0+ server includes the calling
    key's effective scopes for key auth. No scopes reported (older server,
    session, solo) → stay quiet."""
    scopes = me.get("scopes") or None
    if not scopes:
        return None
    excess = sorted(set(scopes) - _MCP_DOORS)
    if not excess:
        return None
    return ("loobric-mcp: this key also grants %s — loobric-mcp never uses "
            "them, but anything holding the key could. A 'read sync assert' "
            "key is safer (loobric create-key --preset agent)."
            % ", ".join(excess))


def _warn_if_over_scoped(client) -> None:
    """Best-effort startup nudge; never blocks startup (Q12: warn, don't
    refuse — and a dead server should fail on the first tool call, with a
    proper MCP error, not here)."""
    try:
        msg = scope_warning(client.whoami())
    except Exception:
        return
    if msg:
        print(msg, file=sys.stderr)


def build_server(client):
    """Wire the SDK-independent registry into an MCP lowlevel Server."""
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from pydantic import AnyUrl

    from loobric.mcp import resources as resources_mod
    from loobric.mcp import tools as tools_mod

    server = Server(
        "loobric", version=_version(),
        instructions=(
            "Tool data for CNC manufacturing on a Loobric Server. Read the "
            "loobric://glossary and loobric://concepts resources before "
            "writing anything. Agents assert, never observe; deletes and "
            "Inbox confirmation are human acts in the Web UI."))

    @server.list_tools()
    async def list_tools() -> list:
        return [types.Tool(name=t.name, description=t.description,
                           inputSchema=t.input_schema)
                for t in tools_mod.TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        result: Any = tools_mod.call_tool(client, name, arguments)
        return [types.TextContent(type="text",
                                  text=json.dumps(result, default=str))]

    @server.list_resource_templates()
    async def list_resource_templates() -> list:
        # No parameterized resource URIs; answer empty rather than -32601 —
        # hosts (MCP Inspector, some agents) probe this method.
        return []

    @server.list_resources()
    async def list_resources() -> list:
        return [types.Resource(uri=AnyUrl(r["uri"]), name=r["name"],
                               description=r["description"],
                               mimeType=r["mimeType"])
                for r in resources_mod.RESOURCES]

    @server.read_resource()
    async def read_resource(uri) -> str:
        for r in resources_mod.RESOURCES:
            if str(uri) == r["uri"]:
                return r["text"]
        raise ValueError(f"Unknown resource: {uri}")

    return server


async def _run() -> None:
    from mcp.server.stdio import stdio_server

    client = _client_from_env()
    _warn_if_over_scoped(client)
    server = build_server(client)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())


def main() -> None:
    try:
        import mcp  # noqa: F401
    except ImportError:
        sys.exit("loobric-mcp needs the optional MCP extra:\n"
                 "  pip install 'loobric-cli[mcp]'")
    import anyio
    anyio.run(_run)


if __name__ == "__main__":
    main()
