# MIT License
# Copyright (c) 2026 sliptonic
# SPDX-License-Identifier: MIT
"""The batch sync verbs (server >= 0.15.0, loobric-server docs/BATCH_SYNC.md):
one request per chunk, per-item tuples back, transparent chunking at the
server's cap."""
from loobric import Client


def _fake(calls):
    def transport(method, endpoint, body=None, **kw):
        calls.append((method, endpoint, body))
        return {"items": [{"client_item_id": i.get("client_item_id"),
                           "id": "rec-%d" % n, "result": "created"}
                          for n, i in enumerate(body["items"])]}
    return transport


def test_sync_tool_records_shape():
    calls = []
    client = Client(base_url="http://example", transport=_fake(calls))
    items = [{"client_item_id": "g-1", "data": {"tool": {}},
              "asserts": [{"path": "name", "value": "x"}]}]
    out = client.sync_tool_records("fusion360", items,
                                   client_version="0.2.0")
    [(method, endpoint, body)] = calls
    assert (method, endpoint) == ("POST", "/tool-instance-records/sync")
    assert body["client"] == "fusion360"
    assert body["client_version"] == "0.2.0"
    assert "actor" not in body                 # defaults server-side
    assert out[0]["result"] == "created"


def test_sync_catalog_records_carries_actor_and_include():
    calls = []
    client = Client(base_url="http://example", transport=_fake(calls))
    client.sync_catalog_records("cli", [{"client_item_id": "PC-1",
                                         "data": {}}],
                                actor="amana", include_records=True)
    [(_, endpoint, body)] = calls
    assert endpoint == "/tool-catalog-records/sync?include=records"
    assert body["actor"] == "amana"


def test_batch_chunks_at_server_cap():
    calls = []
    client = Client(base_url="http://example", transport=_fake(calls))
    items = [{"client_item_id": "g-%d" % i, "data": {}} for i in range(450)]
    out = client.sync_tool_records("fusion360", items)
    assert [len(body["items"]) for _, _, body in calls] == [200, 200, 50]
    assert len(out) == 450                     # results concatenated in order
    assert out[0]["client_item_id"] == "g-0"
    assert out[-1]["client_item_id"] == "g-449"
