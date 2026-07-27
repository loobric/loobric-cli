# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Key-scope presets (SCOPES_PLAN Q5/Q11) and the loobric-mcp least-privilege
startup warning (Q12).

Server 0.6.0 enforces door scopes and requires explicit scopes at key
creation; the presets make the right choice one word. The agent preset is
read+sync+assert — deliberately without observe, bind, or delete."""
import pytest

from loobric.cli.main import PRESET_SCOPES, resolve_scopes
from loobric.mcp.main import scope_warning

AGENT = ["read", "sync", "assert"]


def test_presets_encode_the_door_model():
    assert PRESET_SCOPES["agent"] == AGENT
    assert PRESET_SCOPES["controller"] == ["read", "sync", "observe"]
    assert PRESET_SCOPES["cam"] == AGENT
    assert PRESET_SCOPES["full"] == ["read", "sync", "observe", "assert",
                                     "bind", "delete"]
    for scopes in PRESET_SCOPES.values():
        assert "admin" not in scopes           # admin is never a preset


def test_resolve_scopes_precedence_and_errors():
    # explicit --scopes wins over --preset
    assert resolve_scopes("read sync", "agent") == ["read", "sync"]
    assert resolve_scopes(None, "agent") == AGENT
    assert resolve_scopes(None, None) is None   # server will 400 with advice
    with pytest.raises(SystemExit):
        resolve_scopes(None, "banana")


def test_mcp_scope_warning_flags_excess_doors():
    msg = scope_warning({"scopes": ["read", "sync", "assert", "delete",
                                    "bind"]})
    assert "delete" in msg and "bind" in msg
    assert "read sync assert" in msg           # names the safer key


def test_mcp_scope_warning_quiet_when_least_privilege_or_unknown():
    assert scope_warning({"scopes": AGENT}) is None
    assert scope_warning({"scopes": ["read"]}) is None   # narrower is fine
    assert scope_warning({}) is None           # pre-0.6.0 server: no scopes
    assert scope_warning({"scopes": None}) is None


def test_mcp_startup_names_the_dead_credential():
    """Three of the first four field sessions failed on a dead/mis-wired
    credential, and the agent could only report 'everything 401s'. The
    startup check must turn a 401 into a loud, specific stderr message —
    naming the restart requirement and the config-shadowing footgun — so
    the failure is diagnosed at connect time, not mid-task."""
    from loobric.errors import HTTPError
    from loobric.mcp.main import credential_failure_message
    msg = credential_failure_message(HTTPError(401, "Authentication required"))
    assert "401" in msg
    assert "restart" in msg.lower()            # env is read at startup only
    assert "project-scoped" in msg             # the ~/.claude.json shadow bug
    assert "LOOBRIC_BASE_URL" in msg           # key/server mismatch
    # anything that isn't a credential rejection stays quiet — the server
    # may simply be down, and the first tool call will say so properly
    assert credential_failure_message(HTTPError(500, "boom")) is None
    assert credential_failure_message(OSError("refused")) is None
