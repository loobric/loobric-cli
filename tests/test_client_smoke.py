# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Smoke tests for the extracted library: it imports, dispatches through its
transport, and keeps the call-time transport hook so tests can patch it."""
from loobric import AuthRequired, Client, NotFound, LoobricClientError


def test_injected_transport_receives_calls():
    calls = []

    def fake(method, endpoint, **kw):
        calls.append((method, endpoint))
        return {"items": [{"id": "abc"}]}

    client = Client(base_url="http://example", transport=fake)
    client.list_tool_sets()
    assert calls and calls[0][0] == "GET"


def test_patching_transport_make_request_intercepts(monkeypatch):
    import loobric.transport as transport

    seen = {}

    def fake_make_request(method, endpoint, **kw):
        seen["call"] = (method, endpoint)
        return {"items": []}

    monkeypatch.setattr(transport, "make_request", fake_make_request)
    Client(base_url="http://example").list_machines()
    assert seen["call"][0] == "GET"


def test_key_info_hits_auth_key():
    calls = []

    def fake(method, endpoint, **kw):
        calls.append((method, endpoint))
        return {"channel": "api-key", "api_key_id": "k1",
                "name": "shop", "scopes": ["read"],
                "read_only": True, "legacy": False,
                "user_id": "u1", "email": "e@x"}

    info = Client(base_url="http://example", transport=fake).key_info()
    assert calls == [("GET", "/auth/key")]
    assert info["read_only"] is True


def test_error_hierarchy_exported():
    assert issubclass(NotFound, LoobricClientError)
    assert issubclass(AuthRequired, LoobricClientError)
