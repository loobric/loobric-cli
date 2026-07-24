# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""The Loobric MCP server: lets AI agents (any MCP host) read and write tool
data on a Loobric Server through the public API's audited doors.

Locked design (MCP_PLAN.md, grilled 2026-07-24):
- every agent write is stamped ``asserted:<agent>@mcp`` — attributed, audited
- agents assert, never observe (``observed`` requires a deterministic
  pipeline from measurement to value; an LLM in the loop means assert)
- no deletes, no Inbox confirmation, no bind/unbind, no credential management
- asserts never overwrite a machine-measured (``observed``) value — the
  guard refuses client-side before any request is made

The registry (``tools``) is SDK-independent; ``main`` wires it to the MCP
SDK, which ships as the optional ``loobric-cli[mcp]`` extra so the base
package stays stdlib-only.
"""
