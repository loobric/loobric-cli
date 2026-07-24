# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Client verb for the audit log query endpoint (GET /api/v1/audit-logs).

Added for the MCP server's query_audit_logs tool (MCP_PLAN.md §3): the
reference client grows the verb first, per the standing rule.

Assumptions:
- Filters are passed as query parameters; absent filters are omitted
- The server shape is {logs, total_count, limit, offset, is_admin}
"""
from loobric import Client


def _client_with_capture(calls):
    def fake(method, endpoint, **kw):
        calls.append((method, endpoint))
        return {"logs": [], "total_count": 0, "limit": 100, "offset": 0}
    return Client(base_url="http://example", transport=fake)


def test_query_audit_logs_passes_filters():
    calls = []
    client = _client_with_capture(calls)
    client.query_audit_logs(entity_type="tool_instance_record",
                            operation="ASSERT", limit=5)
    method, endpoint = calls[0]
    assert method == "GET"
    assert endpoint.startswith("/audit-logs?")
    assert "entity_type=tool_instance_record" in endpoint
    assert "operation=ASSERT" in endpoint
    assert "limit=5" in endpoint
    assert "entity_id" not in endpoint


def test_query_audit_logs_no_filters():
    calls = []
    client = _client_with_capture(calls)
    result = client.query_audit_logs()
    assert calls[0][1].rstrip("?") == "/audit-logs"
    assert result["logs"] == []
