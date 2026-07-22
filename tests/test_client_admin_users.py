# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Tests for the admin account-roster verb (`loobric list-users`).

list_users() is a thin door onto GET /api/v1/admin/users — the read-only
"how many accounts exist, and who are they?" roster. We inject a fake transport
and assert the method/endpoint it emits, and that an older server (NotFound)
propagates so the CLI can report it cleanly."""
import pytest

from loobric import Client, NotFound


def test_list_users_hits_admin_users_endpoint():
    calls = []

    def fake(method, endpoint, **kw):
        calls.append((method, endpoint))
        return {"total": 2, "users": [{"email": "a@x"}, {"email": "b@x"}]}

    client = Client(base_url="http://example", transport=fake)
    result = client.list_users()

    assert calls == [("GET", "/admin/users")]
    assert result["total"] == 2
    assert len(result["users"]) == 2


def test_list_users_propagates_notfound_on_older_server():
    def fake(method, endpoint, **kw):
        raise NotFound(404, "no such endpoint")

    client = Client(base_url="http://example", transport=fake)
    with pytest.raises(NotFound):
        client.list_users()
