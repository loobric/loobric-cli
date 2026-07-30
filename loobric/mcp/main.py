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


def credential_failure_message(exc: Exception) -> "str | None":
    """A loud, specific message when the configured credential is rejected
    outright (HTTP 401) — the single most common field failure (three of the
    first four real sessions). Names the actual causes in likelihood order.

    Anything that isn't a 401 returns None: a down server or a scope
    refusal should surface on the first tool call, with a proper error,
    not at startup."""
    from loobric.errors import HTTPError
    if isinstance(exc, HTTPError) and exc.status == 401:
        return (
            "loobric-mcp: the server rejected this credential (HTTP 401) — "
            "every tool call will fail until it is fixed. Check, in order: "
            "(1) the MCP host was restarted after the key changed (env is "
            "read at startup only); (2) LOOBRIC_API_KEY in the config that "
            "actually applies — a project-scoped MCP entry overrides the "
            "global one (check ~/.claude.json for stale or placeholder "
            "entries); (3) LOOBRIC_BASE_URL points at the server the key "
            "was created on; (4) the key wasn't revoked.")
    return None


def _startup_credential_check(client) -> None:
    """Best-effort startup check; never blocks startup (SCOPES_PLAN Q12:
    warn, don't refuse). A dead credential gets the loud 401 message; a
    healthy over-scoped key gets the least-privilege nudge."""
    try:
        me = client.whoami()
    except Exception as exc:
        msg = credential_failure_message(exc)
        if msg:
            print(msg, file=sys.stderr)
        return
    msg = scope_warning(me)
    if msg:
        print(msg, file=sys.stderr)


def build_server(client):
    """Wire the SDK-independent registry into an MCP lowlevel Server."""
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from pydantic import AnyUrl

    from loobric.mcp import resources as resources_mod
    from loobric.mcp import tools as tools_mod

    # SDK compatibility guard: the 2.0 SDK removed the 1.x low-level Server
    # decorator API this function builds on. Without this check the crash is
    # a bare AttributeError deep in a traceback (seen in the field,
    # 2026-07-30); with it, the operator gets the one-line fix.
    if not hasattr(Server, "list_tools"):
        import importlib.metadata
        raise SystemExit(
            "loobric-mcp: installed 'mcp' SDK %s is unsupported (its 1.x "
            "low-level server API is gone). Fix: pip install 'mcp>=1.0,<2'"
            % importlib.metadata.version("mcp"))

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
    _startup_credential_check(client)
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
