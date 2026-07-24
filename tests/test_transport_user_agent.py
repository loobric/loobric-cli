# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""The transport must send an explicit User-Agent on every request.

Cloudflare blocks default Python user agents (error 1010) in front of
api.loobric.com — the smooth-linuxcnc 0.6.1 incident. An explicit
``loobric-cli/<version>`` UA is therefore a correctness requirement, not
cosmetics. Callers (e.g. the MCP server) may override it via extra_headers.

Assumptions:
- make_request always sets User-Agent, defaulting to "loobric-cli/<version>"
- An extra_headers User-Agent wins over the default
- The version comes from installed package metadata, "unknown" when absent
"""
import json

import loobric.transport as transport


class _FakeResponse:
    status = 200

    def read(self):
        return json.dumps({}).encode()

    def getheader(self, name):
        return None


class _FakeConnection:
    def __init__(self):
        self.captured_headers = None

    def request(self, method, path, body=None, headers=None):
        self.captured_headers = dict(headers or {})

    def getresponse(self):
        return _FakeResponse()

    def close(self):
        pass


def _capture_headers(monkeypatch, **kw):
    conn = _FakeConnection()
    monkeypatch.setattr(transport, "get_connection", lambda base_url=None: conn)
    transport.make_request("GET", "/version", base_url="http://example", **kw)
    return conn.captured_headers


def test_user_agent_sent_by_default(monkeypatch):
    headers = _capture_headers(monkeypatch)
    assert "User-Agent" in headers
    assert headers["User-Agent"].startswith("loobric-cli/")


def test_user_agent_override_via_extra_headers(monkeypatch):
    headers = _capture_headers(
        monkeypatch, extra_headers={"User-Agent": "loobric-mcp/0.1"})
    assert headers["User-Agent"] == "loobric-mcp/0.1"
