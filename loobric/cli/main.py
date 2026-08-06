#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Loobric client CLI — an argparse shell over loobric.Client.

The universal command-line client: `loobric <verb>`. Commands build a Client from
the CLI's current config (transport.BASE_URL / API_KEY / session) so they
exercise the same library other clients import.
"""
import argparse
import getpass
import json
import os
import sys
from typing import Any, Dict, List, Optional

from loobric import transport
from loobric.client import Client
from loobric.errors import (
    AuthRequired, ConnectionFailed, HTTPError, NotFound, LoobricClientError,
)


def _client() -> Client:
    """Build a Client from the CLI's current global config (transport.BASE_URL/transport.API_KEY/
    session). Used by the CLI shell so its commands exercise the same library
    other clients import."""
    return Client(base_url=transport.BASE_URL, api_key=transport.API_KEY, session_cookie=transport.SESSION_COOKIE)


def register(email: str = None, password: str = None):
    """Register a new user account.
    
    First user registration is open. Subsequent registrations require admin auth.
    
    Args:
        email: User email address (will prompt if not provided)
        password: User password (will prompt if not provided)
    """
    # Prompt for email if not provided
    if not email:
        email = input("Email: ").strip()
        if not email:
            print("Error: Email is required", file=sys.stderr)
            sys.exit(1)
    
    # Prompt for password if not provided
    if not password:
        password = getpass.getpass("Password: ")
        if not password:
            print("Error: Password is required", file=sys.stderr)
            sys.exit(1)
        # Confirm password
        password_confirm = getpass.getpass("Confirm Password: ")
        if password != password_confirm:
            print("Error: Passwords do not match", file=sys.stderr)
            sys.exit(1)
    
    data = _client().register(email, password)
    # Pin the server we registered against so the next command targets it
    # without re-passing --base-url (login would do this, but a user may run
    # other commands between register and login).
    if transport.BASE_URL:
        transport.save_base_url(transport.BASE_URL, email=email)
    print("✓ Registration successful!")
    print(f"  User: {data.get('email', 'Unknown')}")
    if data.get('id'):
        print(f"  User ID: {data.get('id')}")
    print("\nYou can now login with:")
    print(f"  loobric login {email}")


def login(email: str = None, password: str = None, base_url: str = None):
    """Authenticate and capture session cookie.
    
    Args:
        email: User email address (will prompt if not provided)
        password: User password (will prompt if not provided)
        base_url: Base URL (will prompt if not provided and not in session)
    """
    
    # Prompt for base URL if not provided
    if base_url:
        transport.BASE_URL = base_url.rstrip("/")
    elif not transport.BASE_URL:
        url_input = input("Base URL [http://127.0.0.1:8000]: ").strip()
        if not url_input:
            url_input = "http://127.0.0.1:8000"
        transport.BASE_URL = url_input.rstrip("/")
    
    # Prompt for email if not provided
    if not email:
        email = input("Email: ").strip()
        if not email:
            print("Error: Email is required", file=sys.stderr)
            sys.exit(1)
    
    # Prompt for password if not provided
    if not password:
        password = getpass.getpass("Password: ")
        if not password:
            print("Error: Password is required", file=sys.stderr)
            sys.exit(1)
    
    data = _client().login(email, password)
    print("✓ Login successful!")
    print(f"  User: {data.get('email', 'Unknown')}")
    if data.get('id'):
        print(f"  User ID: {data.get('id')}")
    if not transport.SESSION_COOKIE:
        print("⚠ Warning: No session cookie received. Authentication may have failed.", file=sys.stderr)
    else:
        transport.save_session(email=email)
        print(f"  Session saved to {transport.SESSION_FILE}")
        print(f"  Base URL: {transport.BASE_URL}")


# Door-scope presets (server 0.6.0, SCOPES_PLAN): a key holds the DOORS it
# may use. The agent preset deliberately lacks observe/bind/delete — agents
# assert, never observe, and never confirm bindings or delete. No preset
# grants admin; ask for it explicitly with --scopes if you truly need it.
PRESET_SCOPES = {
    "agent":      ["read", "sync", "assert"],
    "controller": ["read", "sync", "observe"],
    "cam":        ["read", "sync", "assert"],
    "full":       ["read", "sync", "observe", "assert", "bind", "delete"],
}


def resolve_scopes(scopes: Optional[str],
                   preset: Optional[str]) -> Optional[list]:
    """Explicit --scopes wins; else the preset; else None (the 0.6.0 server
    answers a scope-less create with a 400 that names the door vocabulary)."""
    if scopes:
        return scopes.strip().split()
    if preset:
        if preset not in PRESET_SCOPES:
            sys.exit("Unknown preset %r — one of: %s"
                     % (preset, ", ".join(sorted(PRESET_SCOPES))))
        return PRESET_SCOPES[preset]
    return None


def create_key(
    name: str,
    scopes: Optional[str] = None,
    tags: Optional[str] = None,
    expires_at: Optional[str] = None,
    preset: Optional[str] = None
):
    """Create a new API key.

    Args:
        name: Descriptive name for the API key
        scopes: Space-separated door scopes (e.g. 'read sync assert')
        tags: Space-separated list of tags (e.g., 'production mill-3')
        expires_at: ISO 8601 datetime string for expiration
        preset: Named scope preset (agent / controller / cam / full);
            --scopes wins when both are given
    """
    data = _client().create_key(
        name,
        scopes=resolve_scopes(scopes, preset),
        tags=tags.strip().split() if tags else None,
        expires_at=expires_at,
    )

    # Output the plain API key first (for easy copying/piping)
    print(data.get('key'))
    
    # Then output details to stderr so they don't interfere with key capture
    print("\n✓ API key created successfully!", file=sys.stderr)
    print(f"  ID: {data.get('id')}", file=sys.stderr)
    print(f"  Name: {data.get('name')}", file=sys.stderr)
    print(f"  Scopes: {', '.join(data.get('scopes', []))}", file=sys.stderr)
    if data.get("tags"):
        print(f"  Tags: {', '.join(data.get('tags', []))}", file=sys.stderr)
    if data.get("expires_at"):
        print(f"  Expires: {data.get('expires_at')}", file=sys.stderr)
    print("\n⚠ Warning: Save the key now — it won't be shown again!", file=sys.stderr)
    print("\nTo use this key, set the environment variable:", file=sys.stderr)
    print(f"  export LOOBRIC_API_KEY={data.get('key')}", file=sys.stderr)


def list_keys():
    """List all API keys for the authenticated user."""
    data = _client().list_keys()

    if not data:
        print("No API keys found.")
        return
    
    print("\nAPI Keys:")
    print("-" * 80)
    for key in data:
        print(f"  ID: {key.get('id')}")
        print(f"  Name: {key.get('name')}")
        print(f"  Status: {'active' if key.get('is_active', True) else 'REVOKED'}")
        print(f"  Scopes: {', '.join(key.get('scopes', []))}")
        if key.get('tags'):
            print(f"  Tags: {', '.join(key.get('tags', []))}")
        if key.get('created_at'):
            print(f"  Created: {key.get('created_at')}")
        if key.get('expires_at'):
            print(f"  Expires: {key.get('expires_at')}")
        if key.get('last_used_at'):
            print(f"  Last Used: {key.get('last_used_at')}")
        print("-" * 80)


def revoke_key(key_id: str):
    """Revoke an API key (soft: the row stays listed as revoked).

    Args:
        key_id: The ID of the key to revoke
    """
    _client().revoke_key(key_id)
    print(f"✓ API key {key_id} revoked. It stays listed as revoked; "
          f"`loobric delete-key` removes it for good.")


def delete_key(handle: str, assume_yes: bool = False):
    """Permanently delete a REVOKED API key (two deliberate steps: an active
    key must be revoked first, so a working credential can never go straight
    to gone). Audit rows keep the key's id; only the row disappears."""
    key = _resolve_key(handle)
    label = key.get("name") or str(key.get("id"))[:8]
    if key.get("is_active", True):
        print(f"Error: key '{label}' is still active — revoke it first "
              f"(`loobric revoke-key {key.get('id')}`), then delete.",
              file=sys.stderr)
        sys.exit(1)
    if not _confirm(f"Permanently delete revoked key '{label}'? "
                    f"Audit history keeps its id; the row is gone for good.",
                    assume_yes):
        print("Aborted.")
        return
    _client().delete_key(key["id"])
    print(f"✓ Deleted revoked key '{label}'.")


def list_tool_sets():
    """List the user's tool sets (v2 facade: /api/v1/tool-set-records)."""
    items = _client().list_tool_sets()

    if not items:
        print("No tool sets found.")
        return

    print(f"\nTool Sets ({len(items)}):")
    print("=" * 80)
    for tool_set in items:
        print(f"  ID: {_rid(tool_set)}")
        print(f"  Name: {_cval(tool_set, 'name')}")
        members = (tool_set.get("canonical") or {}).get("members") or []
        print(f"  Members: {len(members)} tool record(s)")
        if _ival(tool_set, 'updated_at'):
            print(f"  Updated: {_ival(tool_set, 'updated_at')}")
        print(f"  Version: {_ival(tool_set, 'version')}")
        print("=" * 80)


def show_tool_set(set_handle):
    """Show one tool set and its members: each member's number (with the source
    that vouches for it), the tool it points at, and that tool's geometry."""
    s = _resolve_tool_set(set_handle)
    members = (s.get("canonical") or {}).get("members") or []
    print(f"\nTool Set {_rid(s)}")
    print("=" * 78)
    print(f"  Name: {_cval(s, 'name') or '(unnamed)'}")
    active_on = [r["machine_id"] for r in _client().list_setups(status="active")
                 if r["tool_set_id"] == _rid(s)]
    if active_on:
        mnames = {_rid(m): _cval(m, "name") for m in _client().list_machines()}
        where = ", ".join(mnames.get(mid) or mid[:8] for mid in active_on)
        print(f"  Active setup on: {where} — see `loobric status`")
    else:
        print("  Active setup on: no machine — every number is provisional")
    print(f"  Members: {len(members)}")
    if not members:
        print("  (none yet — add tools with 'loobric add-to-set')")
        print("=" * 78)
        return
    tools = {_rid(t): t for t in _client().list_tool_records()}

    def _num(m):
        v = (m.get("number") or {}).get("value")
        return v if v is not None else float("inf")

    for m in sorted(members, key=_num):
        tid = m.get("tool_record_id")
        num = m.get("number") or {}
        t = tools.get(tid)
        tname = (_cval(t, "name") if t else None) or (str(tid)[:8] if tid else "?")
        ndisp = f"T{num['value']}" if num.get("value") is not None else "(no #)"
        dia = _cval(t, "geometry", "diameter") if t else None
        extra = f"  ⌀{dia}" if dia is not None else ""
        state = m.get("state")
        badge = "" if state is None else (
            "  ✓ ok" if state == "satisfied" else f"  ⚠ {state}")
        print(f"  {ndisp:>6}  {tname}{extra}  [{num.get('source', 'unknown')}]{badge}")
    print("=" * 78)


def add_to_set(set_handle, tools, number: Optional[int] = None):
    """Add one or more tools to a tool set (existing members are kept).

    --number N claims tool number N for the tool — the durable CAM↔CNC
    contract the machine's status view reconciles against. One tool only:
    a claim names one position."""
    if number is not None and len(tools) != 1:
        print("Error: --number claims a position for exactly one tool",
              file=sys.stderr)
        sys.exit(1)
    s = _resolve_tool_set(set_handle)
    recs = [_resolve_record(t) for t in tools]
    numbers = {_rid(recs[0]): number} if number is not None else None
    updated = _client().add_to_set(_rid(s), [_rid(r) for r in recs], numbers=numbers)
    n = len((updated.get("canonical") or {}).get("members") or [])
    label = _cval(s, "name") or str(_rid(s))[:8]
    names = ", ".join(_cval(r, "name") or str(_rid(r))[:8] for r in recs)
    claim = f" (claimed T{number})" if number is not None else ""
    print(f"✓ Added {len(recs)} tool(s) to '{label}' — {names}{claim}. Now {n} member(s).")


def remove_from_set(set_handle, tools):
    """Remove one or more tools from a tool set (the rest are kept)."""
    s = _resolve_tool_set(set_handle)
    recs = [_resolve_record(t) for t in tools]
    updated = _client().remove_from_set(_rid(s), [_rid(r) for r in recs])
    n = len((updated.get("canonical") or {}).get("members") or [])
    label = _cval(s, "name") or str(_rid(s))[:8]
    names = ", ".join(_cval(r, "name") or str(_rid(r))[:8] for r in recs)
    print(f"✓ Removed {len(recs)} tool(s) from '{label}' — {names}. Now {n} member(s).")


def list_pending():
    """List inbox items awaiting review (binding proposals).

    The inbox holds what sync could not decide on its own (G2): heuristic
    binding proposals awaiting a human. Resolve with `resolve <id> confirm`
    or `resolve <id> reject`.
    """
    items = _client().list_inbox()
    if not items:
        print("Inbox is empty - nothing pending.")
        return

    print(f"\n{len(items)} unrecognized machine tool(s) - best-guess matches below.")
    print()
    print("This is an identity question, NOT a conflict: the machine reported")
    print("tools the server doesn't recognize yet. Confirming or rejecting")
    print("overwrites NOTHING on either side.")
    print()
    print("  confirm = 'same tool': links the machine entry to the record so")
    print("            future changes route between them. Both keep their data.")
    print("  reject  = 'different tools': drops this suggestion permanently.")
    print("            The entry stays unbound and keeps syncing fine.")
    print("  unsure? = reject. A rejected pair can be linked manually later;")
    print("            a wrong confirm is currently hard to undo.")
    print("=" * 78)
    for item in items:
        entry = item.get("entry", {})
        proposed = item.get("proposed_instance", {})
        print(f"  ID: {item.get('id')[:8]}")
        print(f"  Machine entry: T{entry.get('tool_number')}")
        print(f"  Proposed match: {proposed.get('name')}")
        print(f"  Confidence: {item.get('confidence'):.0%} - {item.get('reason')}")
        print("-" * 78)
    print("Resolve with: loobric resolve <id> confirm|reject")


def resolve_pending(item_id: str, action: str):
    """Confirm or reject an inbox item.

    Accepts unique id prefixes (like git short SHAs): anything shorter than
    a full UUID is matched against the open inbox items client-side.

    Args:
        item_id: Inbox item id or unique prefix (from `pending`)
        action: "confirm" (bind entry to proposed record) or "reject"
    """
    # The confirm/reject responses no longer echo the entry/instance, so resolve
    # the item against the open inbox first — this both supports id prefixes and
    # gives us the details for a friendly message.
    open_items = _client().list_inbox()
    matches = [i for i in open_items if i.get("id", "").startswith(item_id)]
    if not matches:
        print(f"Error: no open inbox item starts with '{item_id}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Error: '{item_id}' is ambiguous ({len(matches)} matches):", file=sys.stderr)
        for m in matches:
            entry = m.get("entry", {})
            print(f"  {m['id'][:8]}  T{entry.get('tool_number')} "
                  f"-> {m.get('proposed_instance', {}).get('name')}", file=sys.stderr)
        sys.exit(1)
    item = matches[0]
    entry = item.get("entry", {})
    proposed = item.get("proposed_instance", {})
    c = _client()
    (c.confirm_proposal if action == "confirm" else c.reject_proposal)(item["id"])
    if action == "confirm":
        print(f"Linked: T{entry.get('tool_number')} and '{proposed.get('name')}' are "
              f"now the same tool. No data was changed on either side; future "
              f"changes will route between them.")
    else:
        print(f"Dismissed: T{entry.get('tool_number')} is not '{proposed.get('name')}'. "
              f"This suggestion won't reappear; the entry stays unbound.")


# ---------------------------------------------------------------------------
# Sectioned-record accessors (docs/TOOL_SCHEMA.md). Every v2 record is the
# three-section shape {internal, canonical, clients}; the server-owned id lives
# at internal.id and every canonical field is a provenance-tagged leaf
# {value, unit?, source}. All listing/parsing routes through these so the CLI
# never reaches for the retired flat top-level fields again.
# ---------------------------------------------------------------------------

def _rid(record: Dict[str, Any]) -> Optional[str]:
    """The server-owned record id: internal.id."""
    return (record.get("internal") or {}).get("id")


def _ival(record: Dict[str, Any], key: str) -> Any:
    """An internal-section value (version, created_at, updated_at, machine_id)."""
    return (record.get("internal") or {}).get(key)


def _cfield(record: Dict[str, Any], *path: str) -> Dict[str, Any]:
    """The canonical leaf at a dotted path, e.g. ('geometry','diameter') ->
    {value, unit?, source}. Returns {} when absent."""
    node = record.get("canonical") or {}
    for p in path:
        node = (node or {}).get(p) or {}
    return node if isinstance(node, dict) else {}


def _cval(record: Dict[str, Any], *path: str) -> Any:
    """The `.value` of the canonical leaf at a dotted path (None when absent)."""
    return _cfield(record, *path).get("value")


def _match_id(items: List[Dict[str, Any]], prefix: str, label: str) -> Dict[str, Any]:
    """Resolve a possibly-abbreviated id against a list (git short-SHA style).

    An exact match wins outright; otherwise a unique prefix match is used.
    Exits with a helpful message on no/ambiguous match. Works on sectioned
    records: the id is internal.id and the human label is canonical.name.value.
    """
    exact = [i for i in items if _rid(i) == prefix]
    if exact:
        return exact[0]
    # An exact, unique name is as good as an id (humans think in names).
    by_name = [i for i in items if _cval(i, "name") == prefix]
    if len(by_name) == 1:
        return by_name[0]
    # Otherwise an id prefix, falling back to a name prefix.
    matches = [i for i in items if str(_rid(i) or "").startswith(prefix)]
    if not matches:
        matches = [i for i in items if str(_cval(i, "name") or "").startswith(prefix)]
    if not matches:
        print(f"Error: no {label} matches '{prefix}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Error: '{prefix}' is ambiguous ({len(matches)} {label}s):", file=sys.stderr)
        for m in matches:
            print(f"  {str(_rid(m))[:8]}  {_cval(m, 'name') or ''}", file=sys.stderr)
        sys.exit(1)
    return matches[0]


def _resolve_machine(prefix: str) -> Dict[str, Any]:
    return _match_id(_client().list_machines(), prefix, "machine")


def _resolve_record(prefix: str) -> Dict[str, Any]:
    return _match_id(_client().list_tool_records(), prefix, "tool record")


def _resolve_tool_set(prefix: str) -> Dict[str, Any]:
    return _match_id(_client().list_tool_sets(), prefix, "tool set")


def _resolve_catalog(handle: str) -> Dict[str, Any]:
    """Resolve a catalog record by id / unique id-prefix / name / product_code
    (same shape as the other resolvers; on ambiguity it prints the candidates).
    A catalog record carries a manufacturer product_code, so humans reach for it
    as readily as the id or name — all three are first-class handles here."""
    items = _client().list_catalog_records()
    # An exact id, name, or product_code wins outright.
    for keyfn in (lambda r: _rid(r),
                  lambda r: _cval(r, "name"),
                  lambda r: _cval(r, "product_code")):
        exact = [r for r in items if keyfn(r) == handle]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            _ambiguous_catalog(handle, exact)
    # Otherwise a unique prefix on the id, the name, or the product_code.
    matches = [r for r in items
               if str(_rid(r) or "").startswith(handle)
               or str(_cval(r, "name") or "").startswith(handle)
               or str(_cval(r, "product_code") or "").startswith(handle)]
    if not matches:
        print(f"Error: no catalog record matches '{handle}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        _ambiguous_catalog(handle, matches)
    return matches[0]


def _ambiguous_catalog(handle: str, candidates: List[Dict[str, Any]]) -> None:
    print(f"Error: '{handle}' is ambiguous ({len(candidates)} catalog records):",
          file=sys.stderr)
    for c in candidates:
        print(f"  {str(_rid(c))[:8]}  {_cval(c, 'name') or ''}  "
              f"{_cval(c, 'product_code') or ''}".rstrip(), file=sys.stderr)
    sys.exit(1)


def _resolve_entry(machine: Dict[str, Any], tool_number: int) -> Dict[str, Any]:
    """Find a machine's tool-table entry record (a sectioned entry) by its
    observed tool number. v2 mutations (bind/unbind/delete-entry) key off
    the entry's own record id, not machine+tool_number, so callers resolve the
    entry first."""
    items = _client().list_entries(_rid(machine))
    for entry in items:
        if _cval(entry, "tool_number") == tool_number:
            return entry
    print(f"Error: machine '{_cval(machine, 'name')}' has no tool T{tool_number}",
          file=sys.stderr)
    sys.exit(1)


def _confirm(message: str, assume_yes: bool) -> bool:
    """Guard a destructive action. --yes skips; non-interactive requires it."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(f"{message}\nRefusing to proceed without confirmation; re-run with --yes.",
              file=sys.stderr)
        sys.exit(1)
    return input(f"{message} [y/N]: ").strip().lower() in ("y", "yes")


def list_machines():
    """List the user's machines (id, name, controller)."""
    items = _client().list_machines()
    if not items:
        print("No machines found.")
        return
    print(f"\nMachines ({len(items)}):")
    print("=" * 78)
    for m in items:
        print(f"  ID: {_rid(m)}")
        print(f"  Name: {_cval(m, 'name')}")
        if _cval(m, "controller_type"):
            print(f"  Controller: {_cval(m, 'controller_type')}")
        print("=" * 78)


def list_tools():
    """List the user's tool instance records (the public facade).

    Empty is ambiguous when a machine has synced: a fresh controller push
    creates tool-table ENTRIES (machine-observed rows) with no tool RECORDS
    behind them, and "no tools" would misread that state. So the empty path
    checks the machines and names what the tables hold instead."""
    c = _client()
    items = c.list_tool_records()
    if not items:
        print("No tool records found.")
        reported = []
        try:
            for m in c.list_machines():
                n = len(c.list_entries(_rid(m)))
                if n:
                    reported.append((_cval(m, "name") or str(_rid(m))[:8], n))
        except Exception:
            reported = []
        for name, n in reported:
            plural = "entries" if n != 1 else "entry"
            print(f"  (machine '{name}' reports {n} tool-table {plural} — "
                  f"`loobric tool-table {name}` to see them; "
                  f"`loobric create-record` turns one into a tool record)")
        return
    print(f"\nTool Records ({len(items)}):")
    print("=" * 78)
    for t in items:
        print(f"  ID: {_rid(t)}")
        print(f"  Name: {_cval(t, 'name')}")
        bits = []
        shape = _cval(t, "geometry", "shape")
        if shape:
            bits.append(str(shape))
        dia = _cfield(t, "geometry", "diameter")
        if dia.get("value") is not None:
            bits.append(f"⌀{dia['value']}{dia.get('unit', '')}")
        if bits:
            print(f"  Geometry: {' · '.join(bits)}")
        print("=" * 78)


def show_tool_table(machine_id: str):
    """List a machine's tool-table entries and their bind state."""
    machine = _resolve_machine(machine_id)
    name = _cval(machine, "name")
    items = _client().list_entries(_rid(machine))
    if not items:
        print(f"{name}: empty tool table.")
        return
    plural = "entries" if len(items) != 1 else "entry"
    print(f"\n{name} tool table ({len(items)} {plural}):")
    print("=" * 78)
    for e in items:
        rec_id = _cval(e, "bound_instance_id")
        state = f"bound -> {str(rec_id)[:8]}" if rec_id else "unbound"
        dia = _cval(e, "offsets", "diameter")
        line = f"  T{_cval(e, 'tool_number')}: {_cval(e, 'description') or '—'}"
        if dia is not None:
            line += f"  ⌀{dia}"
        print(f"{line}  [{state}]")
    print("=" * 78)


def use_set(machine_handle: str, set_handle: Optional[str], none: bool = False):
    """`use-set`: make a tool set the machine's active setup (or --none to end).

    Activation changes NOTHING on either side — no entry, binding, member, or
    number; it only changes what the machine's status view compares against.
    The previous setup ends automatically and survives as history."""
    machine = _resolve_machine(machine_handle)
    m_name = _cval(machine, "name")
    c = _client()
    if none:
        current = c.active_setup(_rid(machine))
        if current is None:
            print(f"'{m_name}' has no active setup.")
            return
        c.end_setup(current["id"])
        print(f"✓ Ended the active setup on '{m_name}'. Nothing else changed.")
        return
    tool_set = _resolve_tool_set(set_handle)
    c.use_set(_rid(machine), _rid(tool_set))
    set_name = _cval(tool_set, "name") or str(_rid(tool_set))[:8]
    print(f"✓ '{m_name}' is now set up for '{set_name}'. Nothing on either side "
          f"was changed — see `loobric status {machine_handle}` for the diff.")


def _fmt_number(field) -> str:
    v = (field or {}).get("value")
    return f"T{v}" if v is not None else "?"


def setup_status(machine_handle: str):
    """`status`: the machine's setup view — ready / needs attention / notes.

    Display only: Loobric never gates anything. Resolution happens through
    normal channels (mount, unload, edit the CAM library) and sync catches up;
    the one software act is confirming identity (`pending`/`resolve`/`bind`)."""
    machine = _resolve_machine(machine_handle)
    m_name = _cval(machine, "name")
    doc = _client().reconciliation(_rid(machine))
    if not doc.get("active"):
        print(f"{m_name} — no active setup.")
        print(f"Pick one with: loobric use-set {machine_handle} <set>")
        return
    att = doc.get("attention") or {}
    important, notes_n = att.get("important", 0), att.get("notes", 0)
    headline = ("READY" if doc.get("ready")
                else f"NOT READY ({important} need attention, {notes_n} note"
                     f"{'s' if notes_n != 1 else ''})")
    print(f"{m_name} — {doc.get('tool_set_name') or '(unnamed set)'} — {headline}")
    print()

    def _line(num: str, name: str, state: str):
        print(f"  {num:<5}{name:<22}{state}")

    for cl in sorted(doc.get("claims") or [],
                     key=lambda c: ((c.get("number") or {}).get("value") is None,
                                    (c.get("number") or {}).get("value") or 0)):
        num = _fmt_number(cl.get("number"))
        name = cl.get("name") or cl.get("tool_record_id", "")[:8]
        state = cl.get("state")
        obs = (cl.get("observed") or {}).get("value")
        claimed = (cl.get("number") or {}).get("value")
        if state == "satisfied":
            detail = "ok"
        elif state == "blocked":
            who = (cl.get("blocked_by") or {}).get("name") or "another tool"
            detail = f"blocked — T{claimed} occupied by '{who}'"
        elif state == "pending bind":
            detail = "pending bind — mounted, confirm identity"
        elif state == "requested":
            detail = "requested — not on machine"
        elif state == "mismounted":
            detail = f"mismounted — CAM says T{claimed}; machine has it at T{obs}"
        else:
            detail = state or ""
        _line(num, name, detail)
    notes = doc.get("notes") or []
    if notes:
        print("  ---- notes ----")
        for n in sorted(notes, key=lambda n: (n.get("number") or {}).get("value") or 0):
            num = _fmt_number(n.get("number"))
            name = n.get("name") or n.get("description") or "—"
            _line(num, name, n.get("state") or "")


def setup_history(machine_handle: str):
    """`setup-history`: which tool sets this machine ran, when, started by whom."""
    machine = _resolve_machine(machine_handle)
    m_name = _cval(machine, "name")
    rows = _client().list_setups(machine_id=_rid(machine))
    if not rows:
        print(f"'{m_name}' has no setup history.")
        return
    set_names = {_rid(s): _cval(s, "name") for s in _client().list_tool_sets()}
    print(f"\n{m_name} setup history ({len(rows)}):")
    print("=" * 78)
    for r in rows:
        name = set_names.get(r["tool_set_id"]) or r["tool_set_id"][:8]
        span = (r.get("activated_at") or "")[:16] + " -> " + \
               (((r.get("ended_at") or "")[:16]) or "now")
        print(f"  {r['status']:<7} {name:<28} {span}")
    print("=" * 78)


def delete_machine(machine_id: str, assume_yes: bool = False):
    """Delete a machine and its tool-table entries (tool records untouched)."""
    machine = _resolve_machine(machine_id)
    name = _cval(machine, "name")
    if not _confirm(
        f"Delete machine '{name}' and its tool-table entries?", assume_yes
    ):
        print("Aborted.")
        return
    _client().delete_machine(_rid(machine))
    print(f"✓ Deleted machine '{name}'. Tool records were not affected.")


def delete_tool(record_id: str, assume_yes: bool = False):
    """Delete a tool record; entries bound to it are unbound, not orphaned."""
    rec = _resolve_record(record_id)
    name = _cval(rec, "name")
    if not _confirm(
        f"Delete tool record '{name}'? Bound machine entries will be unbound "
        f"(their data stays on the machine).", assume_yes
    ):
        print("Aborted.")
        return
    _client().delete_tool_record(_rid(rec))
    print(f"✓ Deleted tool record '{name}'. Any bound entries were unbound; "
          f"their data stays on the machine.")


def delete_entry(machine_id: str, tool_number: int, assume_yes: bool = False):
    """Remove a machine-reported tool-table entry by tool number."""
    machine = _resolve_machine(machine_id)
    name = _cval(machine, "name")
    entry = _resolve_entry(machine, tool_number)
    if not _confirm(
        f"Remove T{tool_number} from '{name}'?", assume_yes
    ):
        print("Aborted.")
        return
    _client().delete_entry(_rid(entry))
    print(f"✓ Removed T{tool_number} from '{name}'. "
          f"If the controller pushes it again, it returns.")


def bind_entry(machine_id: str, tool_number: int, record_id: str):
    """Link an unbound entry to an owned tool record (overwrites nothing)."""
    machine = _resolve_machine(machine_id)
    m_name = _cval(machine, "name")
    entry = _resolve_entry(machine, tool_number)
    rec = _resolve_record(record_id)
    _client().bind_entry(_rid(entry), instance_id=_rid(rec))
    print(f"✓ Linked T{tool_number} @ {m_name} -> '{_cval(rec, 'name')}'. "
          f"Nothing was overwritten on either side.")


def unbind_entry(machine_id: str, tool_number: int):
    """Unbind an entry; it keeps its data and becomes eligible for suggestions."""
    machine = _resolve_machine(machine_id)
    m_name = _cval(machine, "name")
    entry = _resolve_entry(machine, tool_number)
    _client().unbind_entry(_rid(entry))
    print(f"✓ Unbound T{tool_number} @ {m_name}. The entry keeps its data.")


def create_record(args):
    """Context-aware create-record: from a machine entry (-> BOUND instance) or
    from a catalog record (-> UNBOUND instance). The two paths are mutually
    exclusive; the outcome message names which one ran."""
    qa_path = getattr(args, "qa", None)
    cert = getattr(args, "cert", None)
    if getattr(args, "from_catalog", None):
        if args.machine or args.tool_number is not None:
            print("Error: --from-catalog cannot be combined with MACHINE/TOOL_NUMBER",
                  file=sys.stderr)
            sys.exit(1)
        create_record_from_catalog(args.from_catalog, args.name,
                                   qa_path=qa_path, cert=cert)
    else:
        if qa_path or cert:
            print("Error: --qa/--cert are only valid with --from-catalog "
                  "(manufacturer QA is recorded when creating from a catalog record)",
                  file=sys.stderr)
            sys.exit(1)
        if not args.machine or args.tool_number is None:
            print("Error: create-record needs MACHINE TOOL_NUMBER (entry form) "
                  "or --from-catalog CATALOG", file=sys.stderr)
            sys.exit(1)
        create_record_from_entry(args.machine, args.tool_number, args.name)


def create_record_from_entry(machine_id: str, tool_number: int, name: str = None):
    """Mint a new instance record from a entry's observations and bind it, in one
    step. The bind endpoint mints a new instance when no instance_id is given."""
    machine = _resolve_machine(machine_id)
    m_name = _cval(machine, "name")
    entry = _resolve_entry(machine, tool_number)
    result = _client().bind_entry(_rid(entry), name=name)
    bound = (result.get("canonical", {}).get("bound_instance_id") or {}).get("value")
    rec_id = str(bound or "")[:8]
    print(f"✓ Created a record from T{tool_number} @ {m_name} and bound it "
          f"(record {rec_id}).")


def create_record_from_catalog(catalog_handle: str, name: str = None,
                               qa_path: str = None, cert: str = None):
    """Create a new UNBOUND instance from a catalog record (the catalog->instance
    door). The server stamps the catalog_type_id link as asserted:<requester>;
    the instance is left unbound (it sits in no machine entry). The name defaults
    to the catalog record's name unless --name overrides it.

    Optional manufacturer QA: --qa is a geometry-shaped JSON file ({diameter:
    {value, unit}, ...}) and --cert its certificate/serial. --cert is required
    iff --qa is given; the server stamps each measured field
    observed:manufacturer@<serial>."""
    if qa_path and not cert:
        print("Error: --qa requires --cert (the certificate/serial the QA "
              "measurements are recorded against)", file=sys.stderr)
        sys.exit(1)
    if cert and not qa_path:
        print("Error: --cert requires --qa (a certificate needs QA measurements "
              "to certify)", file=sys.stderr)
        sys.exit(1)
    qa = None
    if qa_path:
        with open(qa_path) as f:
            text = f.read().strip()
        try:
            qa = json.loads(text) if text else {}
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON in --qa file: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(qa, dict):
            print("Error: --qa JSON must be a geometry-shaped object", file=sys.stderr)
            sys.exit(1)
    catalog = _resolve_catalog(catalog_handle)
    cat_name = _cval(catalog, "name")
    rec = _client().create_instance_from_catalog(_rid(catalog), name=name,
                                                 qa=qa, cert=cert)
    inst_id = str(_rid(rec) or "")[:8]
    qa_note = f" with manufacturer QA ({cert})" if qa else ""
    print(f"✓ Created instance {inst_id} from {cat_name}{qa_note} — unbound "
          f"(no machine entry yet).")


def create_machine(name, controller=None):
    """Create a machine and assert its name (and optional controller)."""
    rec = _client().create_machine(name=name, controller_type=controller)
    print(f"✓ Created machine '{name}' ({str(_rid(rec))[:8]}).")
    if controller:
        print(f"  Controller: {controller}")


def create_set(name):
    """Create a tool set and assert its name."""
    rec = _client().create_tool_set(name=name)
    print(f"✓ Created tool set '{name}' ({str(_rid(rec))[:8]}).")


def _load_catalog_fields(file=None) -> Dict[str, Any]:
    """Read the nominal-fields JSON for a catalog record: from --file, else from
    stdin (the '-' convention). An empty/absent stream is an empty object — the
    convenience flags may supply every field by hand. The JSON carries values +
    units; provenance is never in it (the server stamps it from --source)."""
    if file:
        with open(file) as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        text = ""
    text = text.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for catalog record: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print("Error: catalog record JSON must be an object", file=sys.stderr)
        sys.exit(1)
    return data


def _flag_field(fields: Dict[str, Any], key: str, value: Any) -> None:
    """A convenience flag supplies/overrides a top-level nominal field's value,
    keeping any unit already present in the JSON."""
    if value is None:
        return
    leaf = fields.get(key)
    if isinstance(leaf, dict):
        leaf["value"] = value
    else:
        fields[key] = {"value": value}


def create_catalog_record(source, file=None, name=None, manufacturer=None,
                          product_code=None, diameter=None, flutes=None):
    """Create a catalog record (a ToolCatalogRecord) in one atomic, audited call.

    Nominal fields arrive as JSON on stdin (the '-' convention) or via --file,
    with thin convenience flags (--name/--manufacturer/--product-code/--diameter/
    --flutes) for the by-hand case. --source is the declared actor; the server
    stamps `asserted:<source>` on every field — the client never writes
    provenance. name, manufacturer and product_code are required (the identity
    floor)."""
    fields = _load_catalog_fields(file)
    _flag_field(fields, "name", name)
    _flag_field(fields, "manufacturer", manufacturer)
    _flag_field(fields, "product_code", product_code)
    if diameter is not None:
        fields.setdefault("geometry", {})["diameter"] = {"value": diameter, "unit": "mm"}
    if flutes is not None:
        fields.setdefault("geometry", {})["flutes"] = {"value": flutes}
    rec = _client().create_catalog_record(source=source, fields=fields)
    print(f"✓ Created catalog record '{_cval(rec, 'name')}' "
          f"({str(_rid(rec))[:8]}). Every field carries source "
          f"'asserted:{source}'.")


def list_catalog_records():
    """List the user's catalog records (ToolCatalogRecords)."""
    items = _client().list_catalog_records()
    if not items:
        print("No catalog records found.")
        return
    print(f"\nCatalog Records ({len(items)}):")
    print("=" * 78)
    for c in items:
        print(f"  ID: {_rid(c)}")
        print(f"  Name: {_cval(c, 'name')}")
        ident = "  ".join(p for p in (_cval(c, "manufacturer"),
                                      _cval(c, "product_code")) if p)
        if ident:
            print(f"  {ident}")
        dia = _cfield(c, "geometry", "diameter")
        if dia.get("value") is not None:
            print(f"  Geometry: ⌀{dia['value']}{dia.get('unit', '')}")
        print("=" * 78)


def _print_draft(draft):
    """Show the canonical fields a parsed draft would create (dry-run view)."""
    cls = f" [{draft.source_class}]" if draft.source_class else ""
    print(f"  • {draft.name or '(unnamed)'}{cls}")
    ident = "  ".join(p for p in (draft.manufacturer, draft.product_code) if p)
    if ident:
        print(f"      {ident}")
    geom = draft.fields.get("geometry") or {}
    for key, leaf in geom.items():
        if isinstance(leaf, dict):
            unit = leaf.get("unit", "")
            print(f"      {key}: {leaf.get('value')}{unit}")
    if draft.media:
        roles = ", ".join(sorted({m.role for m in draft.media}))
        print(f"      media: {len(draft.media)} file(s) [{roles}]")
    missing = draft.missing_identity()
    if missing:
        print(f"      ! missing identity: {', '.join(missing)} — would be skipped")


def import_tools(path, source=None, dry_run=False, no_preserve=False):
    """Import tool data from a known format into catalog records.

    Detects the format: DIN 4000 (CSV/XML), STEP P21, or a GTC package (.zip,
    ISO 13399 — also carries 3D models/images as canonical media). Parsing is
    offline; --dry-run shows exactly what would be created without sending. Each
    record's full source payload is preserved in its client section unless
    --no-preserve is given."""
    from loobric import importers
    from loobric.importers.run import import_drafts

    try:
        drafts = importers.parse(path)
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    if not drafts:
        print("No tool records found in the file.")
        return

    if dry_run:
        print(f"Parsed {len(drafts)} record(s) from {path} "
              f"(dry run — nothing sent):")
        for draft in drafts:
            _print_draft(draft)
        return

    def on_event(kind, draft, info):
        name = draft.name or "(unnamed)"
        if kind == "create":
            print(f"  ✓ created {name} [{str(info)[:8]}]")
        elif kind == "skip":
            print(f"  – skipped {name}: {info}")
        elif kind == "fail":
            print(f"  ✗ failed {name}: {info}")
        elif kind == "preserve_fail":
            print(f"  ! {name}: created, but preserving raw payload failed: {info}")
        elif kind == "media":
            print(f"      ↑ media: {info.role} ({info.filename})")
        elif kind == "media_fail":
            print(f"      ! media upload failed ({info.filename}): {info}")

    report = import_drafts(_client(), drafts, source=source,
                           preserve=not no_preserve, on_event=on_event)
    print(f"\nImport complete: {len(report.created)} created, "
          f"{len(report.skipped)} skipped, {len(report.failed)} failed"
          f"{f', {report.media_uploaded} media uploaded' if report.media_uploaded else ''}.")


def _print_field(label, leaf, indent="  "):
    """Show one canonical field with its provenance — value, optional unit, and
    the source it came from (the whole point: fabrication stays visible)."""
    value = leaf.get("value")
    unit = leaf.get("unit")
    disp = "—" if value is None else (f"{value} {unit}" if unit else f"{value}")
    print(f"{indent}{label}: {disp}  [{leaf.get('source', '')}]")


def show_catalog_record(catalog):
    """Show one catalog record with full provenance — every field with its source."""
    rec = _resolve_catalog(catalog)
    canonical = rec.get("canonical") or {}
    print(f"\nCatalog Record {_rid(rec)}")
    print("=" * 78)
    for key in ("name", "manufacturer", "product_code", "item_type"):
        leaf = canonical.get(key)
        if isinstance(leaf, dict) and "source" in leaf:
            _print_field(key, leaf)
    geometry = canonical.get("geometry") or {}
    present = {k: v for k, v in geometry.items() if isinstance(v, dict)}
    if present:
        print("  geometry:")
        for gkey, leaf in present.items():
            _print_field(gkey, leaf, indent="    ")
    print("=" * 78)


def show_tool(record_handle):
    """Show one tool instance record with full provenance — every canonical field
    with the source that vouches for it (mirrors show-catalog-record). RECORD
    resolves by id, name, or unique prefix."""
    rec = _resolve_record(record_handle)
    canonical = rec.get("canonical") or {}
    print(f"\nTool Record {_rid(rec)}")
    print("=" * 78)
    for key in ("name", "status", "item_type"):
        leaf = canonical.get(key)
        if isinstance(leaf, dict) and "source" in leaf:
            _print_field(key, leaf)
    # The catalog link is only interesting when the instance actually points at a
    # catalog record (an unbound-to-catalog instance carries a null leaf).
    cat = canonical.get("catalog_type_id")
    if isinstance(cat, dict) and cat.get("value") is not None:
        _print_field("catalog_type_id", cat)
    geometry = canonical.get("geometry") or {}
    present = {k: v for k, v in geometry.items() if isinstance(v, dict)}
    if present:
        print("  geometry:")
        for gkey, leaf in present.items():
            _print_field(gkey, leaf, indent="    ")
    # An assembly carries canonical.components; summarize the parts it is built from.
    components = canonical.get("components")
    if isinstance(components, list) and components:
        print(f"  components: {len(components)} part(s)")
        for comp in components:
            cid = comp.get("tool_record_id") or comp.get("id")
            cname = comp.get("name") or (str(cid)[:8] if cid else "?")
            role = comp.get("role")
            print(f"    {cname}{f' [{role}]' if role else ''}")
    print("=" * 78)


def show_machine(machine_handle):
    """Show one machine with provenance, a summary of its tool table (each
    entry's number, description, and bind state), and any tool sets linked to it.
    MACHINE resolves by id, name, or unique prefix."""
    machine = _resolve_machine(machine_handle)
    canonical = machine.get("canonical") or {}
    print(f"\nMachine {_rid(machine)}")
    print("=" * 78)
    for key in ("name", "controller_type"):
        leaf = canonical.get(key)
        if isinstance(leaf, dict) and "source" in leaf:
            _print_field(key, leaf)
    for section in ("spindle", "coolant"):
        present = {k: v for k, v in (canonical.get(section) or {}).items()
                   if isinstance(v, dict) and "source" in v}
        if present:
            print(f"  {section}:")
            for key, leaf in present.items():
                _print_field(key, leaf, indent="    ")
    entries = _client().list_entries(_rid(machine))
    plural = "entries" if len(entries) != 1 else "entry"
    print(f"  Tool table: {len(entries)} {plural}")
    for e in entries:
        rec_id = _cval(e, "bound_instance_id")
        state = f"bound -> {str(rec_id)[:8]}" if rec_id else "unbound"
        print(f"    T{_cval(e, 'tool_number')}: {_cval(e, 'description') or '—'}  [{state}]")
    setup = _client().active_setup(_rid(machine))
    if setup:
        names = {_rid(s): _cval(s, "name") for s in _client().list_tool_sets()}
        sname = names.get(setup["tool_set_id"]) or setup["tool_set_id"][:8]
        print(f"  Active setup: {sname} (since {(setup.get('activated_at') or '')[:16]})"
              f" — see `loobric status`")
    else:
        print("  Active setup: none — `loobric use-set` to pick one")
    print("=" * 78)


def _resolve_key(handle: str) -> Dict[str, Any]:
    """Resolve an API key by exact id, unique id-prefix, or name. API keys are
    PLAIN dicts (not sectioned records), so this matches on the flat id/name
    fields rather than internal.id/canonical.name. Exits with a helpful message
    on no/ambiguous match (mirrors _match_id)."""
    keys = _client().list_keys()
    exact = [k for k in keys if k.get("id") == handle]
    if exact:
        return exact[0]
    by_name = [k for k in keys if k.get("name") == handle]
    if len(by_name) == 1:
        return by_name[0]
    matches = [k for k in keys if str(k.get("id") or "").startswith(handle)]
    if not matches:
        matches = [k for k in keys if str(k.get("name") or "").startswith(handle)]
    if not matches:
        print(f"Error: no API key matches '{handle}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Error: '{handle}' is ambiguous ({len(matches)} API keys):", file=sys.stderr)
        for k in matches:
            print(f"  {str(k.get('id'))[:8]}  {k.get('name') or ''}", file=sys.stderr)
        sys.exit(1)
    return matches[0]


def show_key(handle):
    """Show one API key (id, name, status, scopes, tags, dates) — the same block
    list-keys prints. KEY resolves by exact id, unique id-prefix, or name."""
    key = _resolve_key(handle)
    print(f"\nAPI Key {key.get('id')}")
    print("=" * 78)
    print(f"  ID: {key.get('id')}")
    print(f"  Name: {key.get('name')}")
    print(f"  Status: {'active' if key.get('is_active', True) else 'REVOKED'}")
    print(f"  Scopes: {', '.join(key.get('scopes', []))}")
    if key.get('tags'):
        print(f"  Tags: {', '.join(key.get('tags', []))}")
    if key.get('created_at'):
        print(f"  Created: {key.get('created_at')}")
    if key.get('expires_at'):
        print(f"  Expires: {key.get('expires_at')}")
    if key.get('last_used_at'):
        print(f"  Last Used: {key.get('last_used_at')}")
    print("=" * 78)


def _parse_entry(spec):
    """Parse a --entry spec 'N[:description[:diameter]]' into a tool-table entry."""
    parts = spec.split(":")
    try:
        tool_number = int(parts[0])
    except ValueError:
        print(f"Error: bad --entry '{spec}': first field must be a tool number",
              file=sys.stderr)
        sys.exit(1)
    entry = {"tool_number": tool_number}
    if len(parts) > 1 and parts[1]:
        entry["description"] = parts[1]
    if len(parts) > 2 and parts[2]:
        try:
            entry["offsets"] = {"diameter": float(parts[2]), "diameter_unit": "mm"}
        except ValueError:
            print(f"Error: bad --entry '{spec}': diameter must be a number", file=sys.stderr)
            sys.exit(1)
    return entry


def push_table(machine_id, entry_specs, client="loobric", snapshot=False):
    """Push a tool table to a machine — the controller-side sync (stand-in for a
    real controller client). Each --entry is 'N[:description[:diameter]]'."""
    machine = _resolve_machine(machine_id)
    name = _cval(machine, "name") or str(_rid(machine))[:8]
    entries = [_parse_entry(s) for s in (entry_specs or [])]
    res = _client().sync_entries(
        _rid(machine), entries, client=client, machine_name=name,
        mode="snapshot" if snapshot else "merge",
    )
    n = len(res.get("items", []))
    print(f"✓ Pushed {n} tool-table entr{'y' if n == 1 else 'ies'} to '{name}' "
          f"as client '{client}'.")
    removed = res.get("removed_tool_numbers", [])
    if removed:
        print(f"  Removed (snapshot): {', '.join('T' + str(t) for t in removed)}")


def reset_account(assume_yes=False):
    """Wipe ALL tool data for this account (keeps login + API keys)."""
    if not _confirm(
        "Delete ALL tool data for this account (records, sets, machines, "
        "entries)? Login and API keys are kept.", assume_yes
    ):
        print("Aborted.")
        return
    res = _client().reset_account()
    deleted = res.get("deleted", {}) or {}
    total = sum(deleted.values()) if isinstance(deleted, dict) else 0
    detail = ", ".join(f"{k}={v}" for k, v in deleted.items()) if deleted else ""
    print(f"✓ Account reset — deleted {total} item(s).{(' ' + detail) if detail else ''}")


# The server's exact factory-reset confirmation phrase. Mirrored here so the CLI
# can refuse early (and prompt for it) before sending anything.
WIPE_PHRASE = "WIPE ALL DATA AND ACCOUNTS"


def wipe_all(confirm=None):
    """Factory reset (admin): wipe ALL data, accounts, and API keys — including
    the calling admin. Guarded by an exact typed/`--confirm`ed phrase; there is
    no undo."""
    print("⚠ FACTORY RESET — deletes ALL data, ALL accounts, and ALL API keys on")
    print("  the server, INCLUDING your own admin account and key. There is no undo.")
    phrase = confirm
    if phrase is None:
        if not sys.stdin.isatty():
            print(f"Refusing: pass --confirm '{WIPE_PHRASE}' to wipe everything "
                  f"non-interactively.", file=sys.stderr)
            sys.exit(1)
        phrase = input(f"Type '{WIPE_PHRASE}' to confirm: ").strip()
    if phrase != WIPE_PHRASE:
        print("Aborted — confirmation phrase did not match.", file=sys.stderr)
        sys.exit(1)
    res = _client().wipe_all(phrase)
    deleted = res.get("deleted", {}) or {}
    total = sum(deleted.values()) if isinstance(deleted, dict) else 0
    print(f"✓ Wiped everything — deleted {total} row(s) across {len(deleted)} table(s).")
    print("  The server is now empty; the next account to register becomes admin.")
    # Our own session and key were just deleted — drop the local session so a
    # stale cookie isn't reused.
    transport.SESSION_COOKIE = None
    transport.clear_session()


def change_password(current=None, new=None):
    """Change the authenticated user's password (prompts when not given)."""
    if not current:
        current = getpass.getpass("Current password: ")
    if not new:
        new = getpass.getpass("New password: ")
        if new != getpass.getpass("Confirm new password: "):
            print("Error: new passwords do not match", file=sys.stderr)
            sys.exit(1)
    if not new:
        print("Error: new password is required", file=sys.stderr)
        sys.exit(1)
    _client().change_password(current, new)
    print("✓ Password changed.")


def _client_version() -> str:
    """This client package's installed version, or 'unknown' (e.g. when run from
    a source checkout that was never installed)."""
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version("loobric-cli")
        except PackageNotFoundError:
            return "unknown"
    except Exception:
        return "unknown"


def show_version():
    """Show the client and server versions — no login required.

    Unlike `whoami`, this needs no authentication: the server's build comes from
    the unauthenticated /version endpoint. It's the quickest 'are my client and
    server compatible / is my deploy current?' check."""
    print(f"  Client: loobric-cli {_client_version()}")
    if not transport.BASE_URL:
        print("  Server: (no base URL set — pass --base-url or set LOOBRIC_BASE_URL)")
        return
    try:
        v = _client().server_version()
        print(f"  Server: {v.get('version', '?')} ({v.get('commit', '?')})  "
              f"[{transport.BASE_URL}]")
    except NotFound:
        print(f"  Server: unknown — older server with no /version endpoint  "
              f"[{transport.BASE_URL}]")
    except LoobricClientError as e:
        print(f"  Server: unreachable  [{transport.BASE_URL}]  ({e})")


def whoami():
    """Show which server we're talking to, the authenticated account, and the
    server's build identity (the fastest 'is this the server/code I expect?'
    check)."""
    client = _client()
    print(f"  Server: {client.base_url or '(none set)'}")
    me = client.whoami()
    print(f"  Email:  {me.get('email')}")
    print(f"  Role:   {me.get('role')}")
    print(f"  Admin:  {me.get('is_admin')}")
    if me.get("id"):
        print(f"  ID:     {me.get('id')}")
    # Credential introspection (server ≥ 0.8.0): when authed with an API key,
    # say which key, its effective door scopes, and whether it can write —
    # the answer a client otherwise learns from a 403 after the fact.
    try:
        info = client.key_info()
    except (NotFound, LoobricClientError):
        info = None
    if info and info.get("channel") == "api-key":
        print(f"  Key:    {info.get('name') or '(unnamed)'}  "
              f"[{info.get('api_key_id', '?')}]")
        scopes = " ".join(info.get("scopes") or [])
        if info.get("legacy"):
            print(f"  Scopes: {scopes} — LEGACY key (pre-0.6.0), degraded to "
                  f"read-only; create a new key (`loobric create-key --preset …`)")
        elif info.get("read_only"):
            print(f"  Scopes: {scopes} — read-only")
        else:
            print(f"  Scopes: {scopes}")
    # Server build identity — an older server has no /version endpoint, which is
    # itself the answer to "is it running my code?"
    try:
        v = client.server_version()
        print(f"  Build:  {v.get('version', '?')} ({v.get('commit', '?')})")
    except NotFound:
        print("  Build:  unknown — older server with no /version endpoint")


def list_users():
    """Show the admin account roster: how many accounts exist and who they are.

    Admin-only on the server. An older server with no /admin/users endpoint
    surfaces as a clear message rather than a stack trace."""
    try:
        data = _client().list_users()
    except NotFound:
        print("This server has no /admin/users endpoint (older build).")
        return
    users = data.get("users", []) if isinstance(data, dict) else (data or [])
    total = data.get("total", len(users)) if isinstance(data, dict) else len(users)
    print(f"  {total} account(s).")
    for u in users:
        flags = []
        if u.get("is_admin"):
            flags.append("admin")
        if not u.get("is_active", True):
            flags.append("inactive")
        if u.get("is_verified"):
            flags.append("verified")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        when = (u.get("created_at") or "")[:10]
        keys = u.get("api_key_count", 0)
        print(f"  {u.get('email', ''):32}  {u.get('role', ''):12}  "
              f"keys={keys:<3}  {when}{suffix}")


def list_audit(limit=50):
    """Show recent audit-log entries (who changed what, when)."""
    data = _client().list_audit_logs()
    items = data.get("logs", []) if isinstance(data, dict) else (data or [])
    if not items:
        print("No audit entries.")
        return
    for e in list(items)[:limit]:
        when = e.get("created_at") or e.get("timestamp") or ""
        print(f"  {when}  {e.get('operation', ''):8}  "
              f"{e.get('entity_type', '')}  {str(e.get('entity_id', ''))[:8]}")


def backup_export(path=None):
    """Export a full account backup (admin)."""
    data = _client().export_backup()
    text = data if isinstance(data, str) else json.dumps(data, indent=2)
    if path:
        with open(path, "w") as f:
            f.write(text)
        print(f"✓ Backup written to {path}.")
    else:
        print(text)


def backup_import(path):
    """Restore an account backup from a JSON file (admin)."""
    with open(path) as f:
        backup_json = f.read()
    _client().import_backup(backup_json)
    print(f"✓ Backup imported from {path}.")


def assert_canonical(resource, record_id, path, value, actor="human@cli", unit=None):
    """Assert a canonical field (the assert door): loobric assert <resource> <id> <path> <value>."""
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        parsed = value
    rec = _client().assert_field(resource, record_id, path, parsed, actor=actor, unit=unit)
    disp = f"{parsed!r} {unit}" if unit else f"{parsed!r}"
    print(f"✓ Asserted {path}={disp} on {resource}/{str(_rid(rec))[:8]}.")


def ping():
    """Check server health/connectivity."""
    conn = transport.get_connection()
    path = "/api/health"
    headers = {
        "Accept": "application/json",
    }
    
    try:
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        status = response.status
        content = response.read().decode("utf-8")
        
        if 200 <= status < 300:
            data = json.loads(content) if content.strip() else {}
            print("✓ Server is healthy")
            print(f"  Status: {data.get('status', 'ok')}")
            if data.get('version'):
                print(f"  Version: {data.get('version')}")
            print(f"  URL: {transport.BASE_URL}")
        else:
            print(f"✗ Server returned HTTP {status}")
            print(f"  URL: {transport.BASE_URL}")
            sys.exit(1)
    except Exception as e:
        print(f"✗ Server unreachable at {transport.BASE_URL}")
        print(f"  Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


def logout():
    """End session."""
    if not transport.SESSION_COOKIE:
        print("No active session to logout.")
        return

    _client().logout()
    transport.SESSION_COOKIE = None
    transport.clear_session()
    print("✓ Logged out successfully.")
    print(f"  Session cleared from {transport.SESSION_FILE}")


def _run(fn, *args, **kwargs):
    """Run a CLI command, turning library errors into a message + exit code.
    The library raises; the CLI shell is where that becomes user-facing output."""
    try:
        return fn(*args, **kwargs)
    except LoobricClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Loobric API Key Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # First time setup - register a user on fresh database
  loobric --base-url http://127.0.0.1:8000 register admin@example.com
  
  # Interactive login (prompts for URL, email, password)
  loobric --login
  
  # Login with specific URL and email
  loobric --base-url http://127.0.0.1:8000 login user@example.com
  
  # After login, base URL is saved - just run commands
  loobric list-keys
  loobric create-key "My Key" --scopes "read write:items"
  
  # Create a key with tags and expiration
  loobric create-key "Backup Script" \\
    --scopes "read" --tags "backup production" --expires-at "2025-12-31T23:59:59Z"
  
  # Revoke an API key
  loobric revoke-key <key_id>

  # The sync loop, end to end (machine ids/names accept unique prefixes)
  loobric create-machine millstone --controller linuxcnc
  loobric push millstone --entry "3:1/4 downcut:6.35" --entry "7:vee:6.0"
  loobric tool-table millstone
  loobric create-record millstone 3 --name "1/4 downcut"   # mint + bind T3
  loobric bind millstone 7 <record>     # or bind an existing record
  loobric unbind millstone 7

  # Catalog records -> a physical instance (unbound: not in any machine yet)
  loobric create-record --from-catalog B201            # by product code
  loobric create-record --from-catalog B201 --name "1/4 downcut, lot 7"
  loobric create-record --from-catalog B201 \\
    --qa qa.json --cert "kennametal@SN12345"           # + manufacturer QA

  # Inspect (list, then drill into one by id / unique prefix / name)
  loobric list-machines
  loobric show-machine millstone        # + its tool table and linked sets
  loobric list-tools
  loobric show-tool "1/4 downcut"       # one instance with full provenance
  loobric list-tool-sets
  loobric show-tool-set "Aluminum job"
  loobric list-keys
  loobric show-key <key_id>             # one API key (id/prefix/name)
  loobric pending                       # binding proposals awaiting review
  loobric audit --limit 20

  # Tool sets & setups
  loobric create-set "Aluminum job"
  loobric add-to-set "Aluminum job" "1/4 downcut" --number 12
  loobric use-set millstone "Aluminum job"   # the machine's active setup
  loobric status millstone                   # ready / needs attention / notes
  loobric setup-history millstone

  # Canonical assert door
  loobric assert tool-set-records <id> name "Aluminum job v2"

  # Admin / housekeeping
  loobric reset --yes                   # wipe all tool data (keeps login + keys)
  loobric backup-export --out backup.json
  loobric backup-import backup.json
  loobric delete-machine millstone --yes
  loobric ping
  loobric logout

Environment Variables:
  LOOBRIC_BASE_URL - Default base URL (can override with --base-url)
  LOOBRIC_API_KEY  - API key for authentication (alternative to login)
"""
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Interactive login (prompts for URL, email, password)"
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="End current session (clears session cookie)"
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (overrides session cookie and $LOOBRIC_API_KEY)"
    )
    parser.add_argument(
        "--base-url", "-b",
        default=os.environ.get("LOOBRIC_BASE_URL"),
        help="Base API URL (default: $LOOBRIC_BASE_URL or saved session)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    # === register ===
    register_parser = subparsers.add_parser(
        "register",
        help="Register a new user account",
        description="Create a new user account. Use this for the first user on a fresh database."
    )
    register_parser.add_argument("email", nargs="?", help="User email address (will prompt if not provided)")
    register_parser.add_argument(
        "--password", "-p",
        help="Password (will be prompted if not provided)"
    )
    register_parser.set_defaults(func=lambda args: register(
        email=args.email,
        password=args.password
    ))

    # === login ===
    login_parser = subparsers.add_parser(
        "login",
        help="Authenticate with email/password",
        description="Authenticate with email and password to create a session."
    )
    login_parser.add_argument("email", nargs="?", help="User email address (will prompt if not provided)")
    login_parser.add_argument(
        "--password", "-p",
        help="Password (will be prompted if not provided)"
    )
    login_parser.add_argument(
        "--url",
        help="Base URL (will be prompted if not provided)"
    )
    login_parser.set_defaults(func=lambda args: login(
        email=args.email,
        password=args.password,
        base_url=args.url or args.base_url
    ))

    # === create-key ===
    create_parser = subparsers.add_parser("create-key", help="Generate a new API key")
    create_parser.add_argument("name", help="Name for the API key (e.g., 'My App')")
    create_parser.add_argument("--scopes", help="Space-separated door scopes, e.g. 'read sync assert'")
    create_parser.add_argument("--preset", choices=sorted(PRESET_SCOPES),
                               help="Named scope preset: agent (AI/MCP: read sync assert), "
                                    "controller (read sync observe), cam, full")
    create_parser.add_argument("--tags", help="Space-separated tags, e.g., 'production mill-3'")
    create_parser.add_argument("--expires-at", help="ISO datetime, e.g., 2025-12-31T23:59:59Z")
    create_parser.set_defaults(func=lambda args: create_key(
        args.name, args.scopes, args.tags, args.expires_at, args.preset
    ))

    # === list-keys ===
    list_parser = subparsers.add_parser("list-keys", help="List all API keys")
    list_parser.set_defaults(func=lambda _: list_keys())

    # === show-key ===
    show_key_parser = subparsers.add_parser(
        "show-key",
        help="Show one API key (id, name, status, scopes, tags, dates)",
        description="Show a single API key's details. KEY resolves by exact id, "
                    "unique id-prefix, or name.",
    )
    show_key_parser.add_argument("key", help="API key id, unique prefix, or name")
    show_key_parser.set_defaults(func=lambda args: show_key(args.key))

    # === revoke-key ===
    revoke_parser = subparsers.add_parser("revoke-key", help="Revoke an API key")
    revoke_parser.add_argument("key_id", help="ID of the key to revoke")
    revoke_parser.set_defaults(func=lambda args: revoke_key(args.key_id))

    # === delete-key ===
    delete_key_parser = subparsers.add_parser(
        "delete-key", help="Permanently delete a REVOKED API key",
        description="Remove a revoked key's row for good (an active key must "
                    "be revoked first). KEY resolves by id, name, or unique "
                    "prefix. Audit history keeps the key's id.",
    )
    delete_key_parser.add_argument("key", help="Key id, name, or unique prefix")
    delete_key_parser.add_argument("--yes", "-y", action="store_true",
                                   help="Skip the confirmation prompt")
    delete_key_parser.set_defaults(
        func=lambda args: delete_key(args.key, args.yes))

    # === list-tool-sets ===
    list_tool_sets_parser = subparsers.add_parser(
        "list-tool-sets",
        help="List tool sets",
        description="List the user's tool sets (named collections of ToolRecords)."
    )
    list_tool_sets_parser.set_defaults(func=lambda args: list_tool_sets())

    # === show-tool-set ===
    show_tool_set_parser = subparsers.add_parser(
        "show-tool-set",
        help="Show one tool set and its members",
        description="Show a tool set's members — each member's number (with the "
                    "source that vouches for it), the tool, and its geometry. SET "
                    "resolves by id, name, or unique prefix.",
    )
    show_tool_set_parser.add_argument("set", help="Tool set id, name, or unique prefix")
    show_tool_set_parser.set_defaults(func=lambda args: show_tool_set(args.set))

    # === use-set / status / setup-history (setups) ===
    use_set_parser = subparsers.add_parser(
        "use-set",
        help="Make a tool set the machine's active setup (or --none to end)",
        description="Tell Loobric which tool set the machine is being set up "
                    "for. Changes NOTHING on either side — it only changes what "
                    "`status` compares against. The previous setup ends "
                    "automatically and survives as history.",
    )
    use_set_parser.add_argument("machine", help="Machine id, name, or unique prefix")
    use_set_parser.add_argument("set", nargs="?",
                                help="Tool set id, name, or unique prefix")
    use_set_parser.add_argument("--none", action="store_true",
                                help="End the active setup without a replacement")
    use_set_parser.set_defaults(func=lambda args: (
        use_set(args.machine, args.set, none=args.none)
        if (args.none or args.set) else
        use_set_parser.error("provide a SET or --none")))

    status_parser = subparsers.add_parser(
        "status",
        help="The machine's setup view: ready / needs attention / notes",
        description="Compare the machine's tool table against its active "
                    "setup's claims. READY = every claimed tool is mounted, at "
                    "the claimed number, with confirmed identity. Notes are "
                    "informational only and never block readiness. Loobric "
                    "never gates anything — fix lines through normal channels "
                    "(mount/unload/edit the CAM library) and sync catches up.",
    )
    status_parser.add_argument("machine", help="Machine id, name, or unique prefix")
    status_parser.set_defaults(func=lambda args: setup_status(args.machine))

    setup_history_parser = subparsers.add_parser(
        "setup-history",
        help="Which tool sets this machine ran, when, started by whom",
    )
    setup_history_parser.add_argument("machine", help="Machine id, name, or unique prefix")
    setup_history_parser.set_defaults(func=lambda args: setup_history(args.machine))

    # === pending / resolve (v2 inbox) ===
    pending_parser = subparsers.add_parser(
        "pending", help="List inbox items awaiting review (binding proposals)"
    )
    pending_parser.set_defaults(func=lambda _: list_pending())

    resolve_parser = subparsers.add_parser(
        "resolve", help="Confirm or reject an inbox item"
    )
    resolve_parser.add_argument("item_id", help="Inbox item id or unique prefix (see 'pending')")
    resolve_parser.add_argument("action", choices=["confirm", "reject"])
    resolve_parser.set_defaults(func=lambda args: resolve_pending(
        args.item_id, args.action
    ))

    # === machines / tool records / entries (v2 management) ===
    list_machines_parser = subparsers.add_parser(
        "list-machines", help="List machines (id, name, controller)"
    )
    list_machines_parser.set_defaults(func=lambda _: list_machines())

    show_machine_parser = subparsers.add_parser(
        "show-machine",
        help="Show one machine with its tool table and linked tool sets",
        description="Show a machine with provenance, a summary of its tool-table "
                    "entries (number, description, bind state), and any tool sets "
                    "linked to it. MACHINE resolves by id, name, or unique prefix.",
    )
    show_machine_parser.add_argument("machine", help="Machine id, name, or unique prefix")
    show_machine_parser.set_defaults(func=lambda args: show_machine(args.machine))

    list_tools_parser = subparsers.add_parser(
        "list-tools", help="List tool records (the public facade)"
    )
    list_tools_parser.set_defaults(func=lambda _: list_tools())

    show_tool_parser = subparsers.add_parser(
        "show-tool",
        help="Show one tool instance record with provenance",
        description="Show a tool instance record's canonical fields, each with "
                    "the source that vouches for it. RECORD resolves by id, name, "
                    "or unique prefix.",
    )
    show_tool_parser.add_argument("record", help="Tool record id, name, or unique prefix")
    show_tool_parser.set_defaults(func=lambda args: show_tool(args.record))

    tool_table_parser = subparsers.add_parser(
        "tool-table", help="Show a machine's tool-table entries and bind state"
    )
    tool_table_parser.add_argument("machine", help="Machine id or unique prefix")
    tool_table_parser.set_defaults(func=lambda args: show_tool_table(args.machine))

    delete_machine_parser = subparsers.add_parser(
        "delete-machine",
        help="Delete a machine and its tool-table entries (records untouched)",
    )
    delete_machine_parser.add_argument("machine", help="Machine id or unique prefix")
    delete_machine_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip the confirmation prompt"
    )
    delete_machine_parser.set_defaults(func=lambda args: delete_machine(args.machine, args.yes))

    delete_tool_parser = subparsers.add_parser(
        "delete-tool",
        help="Delete a tool record (bound entries are unbound, not orphaned)",
    )
    delete_tool_parser.add_argument("record", help="Tool record id or unique prefix")
    delete_tool_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip the confirmation prompt"
    )
    delete_tool_parser.set_defaults(func=lambda args: delete_tool(args.record, args.yes))

    delete_entry_parser = subparsers.add_parser(
        "delete-entry", help="Remove a machine-reported tool-table entry"
    )
    delete_entry_parser.add_argument("machine", help="Machine id or unique prefix")
    delete_entry_parser.add_argument("tool_number", type=int, help="Tool number (e.g. 3)")
    delete_entry_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip the confirmation prompt"
    )
    delete_entry_parser.set_defaults(
        func=lambda args: delete_entry(args.machine, args.tool_number, args.yes)
    )

    bind_parser = subparsers.add_parser(
        "bind", help="Link an unbound entry to a tool record"
    )
    bind_parser.add_argument("machine", help="Machine id or unique prefix")
    bind_parser.add_argument("tool_number", type=int, help="Tool number (e.g. 3)")
    bind_parser.add_argument("record", help="Tool record id or unique prefix")
    bind_parser.set_defaults(
        func=lambda args: bind_entry(args.machine, args.tool_number, args.record)
    )

    unbind_parser = subparsers.add_parser(
        "unbind", help="Unbind an entry (it keeps its data)"
    )
    unbind_parser.add_argument("machine", help="Machine id or unique prefix")
    unbind_parser.add_argument("tool_number", type=int, help="Tool number (e.g. 3)")
    unbind_parser.set_defaults(
        func=lambda args: unbind_entry(args.machine, args.tool_number)
    )

    create_record_parser = subparsers.add_parser(
        "create-record",
        help="Create a tool instance — from an entry (bound) or a catalog (unbound)",
        description="Two context-aware forms. MACHINE TOOL_NUMBER creates an "
                    "instance from a machine entry and BINDS it to that position. "
                    "--from-catalog creates an instance from a catalog record and "
                    "leaves it UNBOUND (a catalog is not a machine position).",
    )
    create_record_parser.add_argument(
        "machine", nargs="?", help="Machine id or unique prefix (entry form)"
    )
    create_record_parser.add_argument(
        "tool_number", nargs="?", type=int, help="Tool number, e.g. 3 (entry form)"
    )
    create_record_parser.add_argument(
        "--from-catalog", metavar="CATALOG",
        help="Create an UNBOUND instance from a catalog record "
             "(id/prefix/name/product_code)",
    )
    create_record_parser.add_argument(
        "--name",
        help="Name for the new instance (entry form: defaults to the entry "
             "description; catalog form: defaults to the catalog record's name)",
    )
    create_record_parser.add_argument(
        "--qa", metavar="FILE",
        help="Manufacturer QA: a geometry-shaped JSON file ({diameter:{value,"
             "unit}, ...}) measured on the certified tool (catalog form only; "
             "requires --cert)",
    )
    create_record_parser.add_argument(
        "--cert",
        help="Certificate/serial the --qa measurements are recorded against; the "
             "server stamps them observed:manufacturer@<serial> (required iff --qa)",
    )
    create_record_parser.set_defaults(func=create_record)

    # === create-machine ===
    create_machine_parser = subparsers.add_parser(
        "create-machine", help="Create a machine and name it"
    )
    create_machine_parser.add_argument("name", help="Machine name (e.g. millstone)")
    create_machine_parser.add_argument("--controller", help="Controller type (e.g. linuxcnc)")
    create_machine_parser.set_defaults(
        func=lambda args: create_machine(args.name, args.controller)
    )

    # === create-set ===
    create_set_parser = subparsers.add_parser(
        "create-set", help="Create a tool set and name it"
    )
    create_set_parser.add_argument("name", help="Tool set name")
    create_set_parser.set_defaults(func=lambda args: create_set(args.name))

    add_to_set_parser = subparsers.add_parser(
        "add-to-set", help="Add one or more tools to a tool set",
        description="Append tool record(s) to a set's membership. Existing "
                    "members (and their numbers) are kept; a tool already in the "
                    "set is skipped. SET and each TOOL resolve by id, name, or "
                    "unique prefix.",
    )
    add_to_set_parser.add_argument("set", help="Tool set id, name, or unique prefix")
    add_to_set_parser.add_argument("tool", nargs="+",
                                   help="Tool record id(s), name(s), or unique prefix(es)")
    add_to_set_parser.add_argument(
        "--number", type=int,
        help="Claim this tool number for the tool (one tool only) — the "
             "durable CAM↔CNC contract `status` reconciles against")
    add_to_set_parser.set_defaults(
        func=lambda args: add_to_set(args.set, args.tool, number=args.number))

    remove_from_set_parser = subparsers.add_parser(
        "remove-from-set", help="Remove one or more tools from a tool set",
        description="Remove tool record(s) from a set's membership; the rest are "
                    "kept. SET and each TOOL resolve by id, name, or unique prefix.",
    )
    remove_from_set_parser.add_argument("set", help="Tool set id, name, or unique prefix")
    remove_from_set_parser.add_argument("tool", nargs="+",
                                        help="Tool record id(s), name(s), or unique prefix(es)")
    remove_from_set_parser.set_defaults(
        func=lambda args: remove_from_set(args.set, args.tool))

    # === create-catalog-record ===
    create_catalog_parser = subparsers.add_parser(
        "create-catalog-record",
        help="Create a catalog record from JSON (stdin/--file) or flags",
        description="Create a ToolCatalogRecord in one atomic, audited call. "
                    "Nominal fields come from JSON on stdin (the '-' convention) "
                    "or --file, plus convenience flags. --source is the declared "
                    "actor; the server stamps 'asserted:<source>' on every field.",
    )
    create_catalog_parser.add_argument(
        "input", nargs="?",
        help="'-' to read JSON from stdin (default when piped), or a path",
    )
    create_catalog_parser.add_argument(
        "--source", required=True,
        help="Declared actor, e.g. manufacturer:kennametal "
             "(server stamps asserted:<source> on every field)",
    )
    create_catalog_parser.add_argument("--file", help="Read nominal fields JSON from this file")
    create_catalog_parser.add_argument("--name", help="Catalog record name")
    create_catalog_parser.add_argument("--manufacturer", help="Manufacturer")
    create_catalog_parser.add_argument("--product-code", help="Manufacturer product code")
    create_catalog_parser.add_argument("--diameter", type=float, help="Nominal diameter (mm)")
    create_catalog_parser.add_argument("--flutes", type=int, help="Flute count")
    create_catalog_parser.set_defaults(func=lambda args: create_catalog_record(
        source=args.source,
        file=args.file or (args.input if args.input and args.input != "-" else None),
        name=args.name, manufacturer=args.manufacturer,
        product_code=args.product_code, diameter=args.diameter, flutes=args.flutes,
    ))

    # === list-catalog-records ===
    list_catalog_parser = subparsers.add_parser(
        "list-catalog-records", help="List catalog records (ToolCatalogRecords)"
    )
    list_catalog_parser.set_defaults(func=lambda _: list_catalog_records())

    # === show-catalog-record ===
    show_catalog_parser = subparsers.add_parser(
        "show-catalog-record", help="Show one catalog record with provenance"
    )
    show_catalog_parser.add_argument(
        "catalog", help="Catalog record id, unique prefix, name, or product_code"
    )
    show_catalog_parser.set_defaults(func=lambda args: show_catalog_record(args.catalog))

    # === push ===
    push_parser = subparsers.add_parser(
        "push", help="Push a tool table to a machine (controller-side sync)"
    )
    push_parser.add_argument("machine", help="Machine id, name, or unique prefix")
    push_parser.add_argument(
        "--entry", action="append", dest="entries", metavar="N[:DESC[:DIA]]",
        help="A tool-table entry, e.g. --entry '3:1/4 downcut:6.35' (repeatable)"
    )
    push_parser.add_argument("--client", default="loobric",
                             help="Client name stamped on the push (default: loobric)")
    push_parser.add_argument("--snapshot", action="store_true",
                             help="Snapshot mode: entries absent from this push are removed")
    push_parser.set_defaults(
        func=lambda args: push_table(args.machine, args.entries, args.client, args.snapshot)
    )

    # === reset ===
    reset_parser = subparsers.add_parser(
        "reset", help="Wipe all tool data for this account (keeps login + API keys)"
    )
    reset_parser.add_argument("--yes", "-y", action="store_true",
                              help="Skip the confirmation prompt")
    reset_parser.set_defaults(func=lambda args: reset_account(args.yes))

    # === list-users (admin) ===
    list_users_parser = subparsers.add_parser(
        "list-users",
        help="ADMIN: list all accounts — how many exist and who they are",
        description="Admin-only account roster: how many accounts exist and who "
                    "they are (email, role, flags, API-key count, created date), "
                    "newest first. No secrets are shown.",
    )
    list_users_parser.set_defaults(func=lambda _: list_users())

    # === wipe-all (admin factory reset) ===
    wipe_parser = subparsers.add_parser(
        "wipe-all",
        help="ADMIN: wipe ALL data, accounts, and keys — including yours (no undo)",
        description="Factory reset (admin-only): delete ALL data, ALL accounts, "
                    "and ALL API keys on the server, including the calling admin. "
                    "Prompts for an exact confirmation phrase; pass --confirm to "
                    "run non-interactively. There is no undo.",
    )
    wipe_parser.add_argument(
        "--confirm", metavar="PHRASE",
        help=f"The exact phrase '{WIPE_PHRASE}' (required when non-interactive)",
    )
    wipe_parser.set_defaults(func=lambda args: wipe_all(args.confirm))

    # === change-password ===
    change_pw_parser = subparsers.add_parser(
        "change-password",
        help="Change your password (prompts for current + new)",
        description="Change the authenticated user's password. Prompts for the "
                    "current and new password when not given as flags.",
    )
    change_pw_parser.add_argument("--current", help="Current password (prompted if omitted)")
    change_pw_parser.add_argument("--new", help="New password (prompted if omitted)")
    change_pw_parser.set_defaults(func=lambda args: change_password(args.current, args.new))

    # === version ===
    version_parser = subparsers.add_parser(
        "version",
        help="Show client and server versions (no login required)",
        description="Print this client's version and the server's build "
                    "(from the unauthenticated /version endpoint). The quickest "
                    "'are my client and server compatible?' check.",
    )
    version_parser.set_defaults(func=lambda _: show_version())

    # === whoami ===
    whoami_parser = subparsers.add_parser("whoami", help="Show the authenticated account")
    whoami_parser.set_defaults(func=lambda _: whoami())

    # === audit ===
    audit_parser = subparsers.add_parser("audit", help="Show recent audit-log entries")
    audit_parser.add_argument("--limit", type=int, default=50, help="Max entries (default 50)")
    audit_parser.set_defaults(func=lambda args: list_audit(args.limit))

    # === backup-export / backup-import ===
    backup_export_parser = subparsers.add_parser(
        "backup-export", help="Export a full account backup (admin)")
    backup_export_parser.add_argument("--out", help="Write to this file (default: stdout)")
    backup_export_parser.set_defaults(func=lambda args: backup_export(args.out))

    backup_import_parser = subparsers.add_parser(
        "backup-import", help="Restore an account backup from a JSON file (admin)")
    backup_import_parser.add_argument("file", help="Path to the backup JSON file")
    backup_import_parser.set_defaults(func=lambda args: backup_import(args.file))

    # === assert (the canonical assert door) ===
    assert_parser = subparsers.add_parser(
        "assert", help="Assert a canonical field: assert <resource> <id> <path> <value>")
    assert_parser.add_argument("resource", help="e.g. machine-records, tool-set-records")
    assert_parser.add_argument("record_id", help="Record id")
    assert_parser.add_argument("path", help="Canonical path, e.g. name")
    assert_parser.add_argument("value", help="Value (JSON-parsed if possible, else string)")
    assert_parser.add_argument("--unit", help="Unit for the value, e.g. rpm, kW, mm")
    assert_parser.set_defaults(
        func=lambda args: assert_canonical(args.resource, args.record_id, args.path,
                                           args.value, unit=args.unit))

    # === import (format importers) ===
    import_parser = subparsers.add_parser(
        "import",
        help="Import tool data from a known format (DIN 4000, STEP P21, GTC, "
             "SolidCAM, hyperMILL) into catalog records")
    import_parser.add_argument("file", help="Path to the export file (.csv/.xml/.p21/.zip)")
    import_parser.add_argument(
        "--source", default=None,
        help="Declared actor; the server stamps asserted:<source> (default: din4000-import)")
    import_parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and show what would be created, without sending anything")
    import_parser.add_argument(
        "--no-preserve", action="store_true",
        help="Do not store the raw source payload in the record's client section")
    import_parser.set_defaults(func=lambda args: import_tools(
        args.file, source=args.source, dry_run=args.dry_run, no_preserve=args.no_preserve))

    # === ping ===
    ping_parser = subparsers.add_parser(
        "ping",
        help="Check server health",
        description="Check if the server is reachable and healthy."
    )
    ping_parser.set_defaults(func=lambda _: ping())

    # === logout ===
    logout_parser = subparsers.add_parser(
        "logout",
        help="End current session",
        description="End the current session (clears session cookie)."
    )
    logout_parser.set_defaults(func=lambda _: logout())

    # Optional shell tab-completion. argcomplete is NOT a dependency — this file
    # stays stdlib-only and fully runnable without it; when argcomplete is
    # present and registered (see README/CLI.md), it wires up completion for
    # every subcommand and flag derived from this parser. No-op when absent.
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    # Parse args
    args = parser.parse_args()
    
    # Set global state
    
    # Handle --login shortcut
    if args.login:
        _run(login)
        return

    # Handle --logout shortcut
    if args.logout:
        # Load session to get transport.BASE_URL for logout request
        transport.API_KEY = os.environ.get("LOOBRIC_API_KEY")
        if not transport.API_KEY:
            session_data = transport.load_session()
        _run(logout)
        return
    
    # Set transport.BASE_URL from args or environment first (before loading session)
    if args.base_url:
        transport.BASE_URL = args.base_url.rstrip("/")
    
    # Load session first (for session-based auth)
    session_data = transport.load_session()
    
    # API key precedence: --api-key flag > LOOBRIC_API_KEY env > saved session
    # cookie. The env var makes the create-key "export LOOBRIC_API_KEY=…" advice
    # actually take effect without repeating --api-key on every command — the
    # right default for a sandbox, where sessions die on each redeploy but API
    # keys persist. A flag still wins; the transport prefers a key over a cookie.
    if args.api_key:
        transport.API_KEY = args.api_key
    elif os.environ.get("LOOBRIC_API_KEY"):
        transport.API_KEY = os.environ["LOOBRIC_API_KEY"]

    # Validate transport.BASE_URL is set. `version` is exempt: it reports the
    # client version with or without a server, and shows the server build only
    # when a base URL happens to be configured.
    if not transport.BASE_URL and getattr(args, "command", None) != "version":
        print("Error: Base URL required. Set it once and every command targets "
              "that server, e.g.:\n"
              "  export LOOBRIC_BASE_URL=https://api.loobric.com\n"
              "or pass --base-url <url>, or run 'loobric --login' first.",
              file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Base URL: {transport.BASE_URL}", file=sys.stderr)
        if transport.API_KEY:
            src = "--api-key flag" if args.api_key else "$LOOBRIC_API_KEY"
            print(f"Using API key from {src}", file=sys.stderr)
        elif transport.SESSION_COOKIE:
            print(f"Using saved session from {transport.SESSION_FILE}", file=sys.stderr)
        else:
            print(f"No authentication (login required for protected endpoints)", file=sys.stderr)

    # Run command if one was provided
    if hasattr(args, 'func'):
        _run(args.func, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
