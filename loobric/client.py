# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""The Loobric client library: a Client with one method per public API operation.
Returns parsed data; raises LoobricClientError subclasses. Stdlib only.

    from loobric import Client, NotFound
    c = Client(base_url="http://nas:8000", api_key="...")   # solo: omit api_key
    for s in c.list_tool_sets(): ...
"""
import json
from typing import Any, Dict, List, Optional

from loobric import transport as transport_mod
from loobric.errors import (
    AuthRequired, ConnectionFailed, HTTPError, NotFound, LoobricClientError,
)


class Client:
    """A reusable Loobric API client. Returns data; raises LoobricClientError."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 session_cookie: Optional[str] = None, transport=None):
        self.base_url = (base_url or transport_mod.BASE_URL or "").rstrip("/")
        self.api_key = api_key
        self.session_cookie = session_cookie
        # transport(method, endpoint, **kw) -> dict, raising LoobricClientError. Defaults
        # to transport.make_request (real HTTP); a test can inject one that calls the app
        # in-process. None => resolve transport.make_request at call time (so patching the
        # module-level transport.make_request still intercepts).
        self._transport = transport

    def _send(self, method: str, endpoint: str, **kw):
        return (self._transport or transport_mod.make_request)(
            method, endpoint, base_url=self.base_url or None,
            api_key=self.api_key, session_cookie=self.session_cookie, **kw)

    def _call(self, method: str, endpoint: str, body: Optional[Dict[str, Any]] = None,
              require_auth: bool = True) -> Dict[str, Any]:
        return self._send(method, endpoint, body=body, require_auth=require_auth)

    # -- tool sets -----------------------------------------------------------
    def list_tool_sets(self) -> List[Dict[str, Any]]:
        return self._call("GET", "/tool-set-records").get("items", [])

    def get_tool_set(self, record_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/tool-set-records/{record_id}")

    def create_tool_set(self, name: Optional[str] = None,
                        actor: str = "human@cli") -> Dict[str, Any]:
        rec = self._call("POST", "/tool-set-records", body={})
        if name is not None:
            rec = self.assert_field("tool-set-records", rec["internal"]["id"], "name", name, actor)
        return rec

    def delete_tool_set(self, record_id: str) -> Dict[str, Any]:
        return self._call("DELETE", f"/tool-set-records/{record_id}")

    def link_set_to_machine(self, set_id: str, machine_id: str,
                            actor: str = "human@cli") -> Dict[str, Any]:
        return self.assert_field("tool-set-records", set_id, "machine_id", machine_id, actor)

    def set_members(self, set_id: str, members: List[Dict[str, Any]],
                    actor: str = "human@cli") -> Dict[str, Any]:
        """Replace a tool set's membership. `members` is a list of
        `{tool_record_id, number?}`."""
        return self._call("POST", f"/tool-set-records/{set_id}/members",
                          body={"members": members, "actor": actor})

    def _member_payload(self, set_id: str) -> List[Dict[str, Any]]:
        """Current membership as the `{tool_record_id, number}` payload the
        members door expects (number is the bare int, or None for unknown)."""
        rec = self.get_tool_set(set_id)
        out = []
        for m in (rec.get("canonical") or {}).get("members") or []:
            num = m.get("number")
            out.append({"tool_record_id": m["tool_record_id"],
                        "number": num.get("value") if isinstance(num, dict) else num})
        return out

    def add_to_set(self, set_id: str, tool_record_ids: List[str],
                   actor: str = "human@cli") -> Dict[str, Any]:
        """Add tool record(s) to a set, keeping existing members and their
        numbers. Tools already in the set are skipped — membership is a set, not
        a bag. Read-modify-write over the replace-only members door."""
        members = self._member_payload(set_id)
        have = {m["tool_record_id"] for m in members}
        for tid in tool_record_ids:
            if tid not in have:
                members.append({"tool_record_id": tid, "number": None})
                have.add(tid)
        return self.set_members(set_id, members, actor)

    def remove_from_set(self, set_id: str, tool_record_ids: List[str],
                        actor: str = "human@cli") -> Dict[str, Any]:
        """Remove tool record(s) from a set, keeping the rest. Read-modify-write
        over the replace-only members door."""
        drop = set(tool_record_ids)
        members = [m for m in self._member_payload(set_id)
                   if m["tool_record_id"] not in drop]
        return self.set_members(set_id, members, actor)

    # -- machines ------------------------------------------------------------
    def list_machines(self) -> List[Dict[str, Any]]:
        return self._call("GET", "/machine-records").get("items", [])

    def get_machine(self, record_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/machine-records/{record_id}")

    def create_machine(self, name: Optional[str] = None,
                       controller_type: Optional[str] = None,
                       actor: str = "human@cli") -> Dict[str, Any]:
        """Mint a machine, then assert its name/controller (canonical changes go
        through the assert door, never the create)."""
        rec = self._call("POST", "/machine-records", body={})
        rid = rec["internal"]["id"]
        if name is not None:
            rec = self.assert_field("machine-records", rid, "name", name, actor)
        if controller_type is not None:
            rec = self.assert_field("machine-records", rid, "controller_type", controller_type, actor)
        return rec

    def delete_machine(self, record_id: str) -> Dict[str, Any]:
        return self._call("DELETE", f"/machine-records/{record_id}")

    # -- tool (instance) records --------------------------------------------
    def list_tool_records(self) -> List[Dict[str, Any]]:
        return self._call("GET", "/tool-instance-records").get("items", [])

    def get_tool_record(self, record_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/tool-instance-records/{record_id}")

    def delete_tool_record(self, record_id: str) -> Dict[str, Any]:
        return self._call("DELETE", f"/tool-instance-records/{record_id}")

    # -- machine tool-table entries (ToolTableEntry) ------------------------
    def list_entries(self, machine_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if machine_id:
            return self._call(
                "GET", f"/tool-table-entry-records?machine_id={machine_id}").get("items", [])
        return self._call("GET", "/tool-table-entry-records").get("items", [])

    def get_entry(self, record_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/tool-table-entry-records/{record_id}")

    def sync_entries(self, machine_id: str, entries: List[Dict[str, Any]],
                     client: str = "loobric", machine_name: Optional[str] = None,
                     mode: str = "merge", client_version: str = "") -> Dict[str, Any]:
        """The controller-side tool-table push: upsert a machine's tool-table
        entries by tool_number in one call (numbers/offsets observed). Returns
        ``{"items": [...], "removed_tool_numbers": [...]}``.

        ``entries`` is the wire field too (the old server-side term was purged
        with everything else, REBOOT R10)."""
        return self._call("POST", "/tool-table-entry-records/sync", body={
            "machine_id": machine_id, "client": client,
            "machine_name": machine_name or machine_id,
            "client_version": client_version, "mode": mode, "entries": entries,
        })

    def bind_entry(self, entry_id: str, instance_id: Optional[str] = None,
                   name: Optional[str] = None, move: bool = False,
                   actor: Optional[str] = None) -> Dict[str, Any]:
        """Bind an instance into an entry. Omit instance_id to MINT a new
        instance from the entry's observations (the 'new tool' path) and bind it."""
        body: Dict[str, Any] = {}
        if instance_id is not None:
            body["instance_id"] = instance_id
        if name is not None:
            body["name"] = name
        if move:
            body["move"] = True
        if actor is not None:
            body["actor"] = actor
        return self._call("POST", f"/tool-table-entry-records/{entry_id}/bind", body=body)

    def unbind_entry(self, entry_id: str) -> Dict[str, Any]:
        return self._call("POST", f"/tool-table-entry-records/{entry_id}/unbind")

    def delete_entry(self, entry_id: str) -> Dict[str, Any]:
        return self._call("DELETE", f"/tool-table-entry-records/{entry_id}")

    # -- the canonical 'assert' door ----------------------------------------
    def assert_field(self, resource: str, record_id: str, path: str, value: Any,
                     actor: str = "human@cli") -> Dict[str, Any]:
        return self._call("POST", f"/{resource}/{record_id}/assert",
                          body={"path": path, "value": value, "actor": actor})

    # -- inbox ---------------------------------------------------------------
    def list_inbox(self) -> List[Dict[str, Any]]:
        return self._call("GET", "/instance-inbox").get("items", [])

    def confirm_proposal(self, proposal_id: str) -> Dict[str, Any]:
        return self._call("POST", f"/instance-inbox/{proposal_id}/confirm")

    def reject_proposal(self, proposal_id: str) -> Dict[str, Any]:
        return self._call("POST", f"/instance-inbox/{proposal_id}/reject")

    # -- auth & keys ---------------------------------------------------------
    def register(self, email: str, password: str) -> Dict[str, Any]:
        return self._call("POST", "/auth/register",
                          body={"email": email, "password": password}, require_auth=False)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        return self._call("POST", "/auth/login",
                          body={"email": email, "password": password}, require_auth=False)

    def logout(self) -> Dict[str, Any]:
        return self._call("POST", "/auth/logout", require_auth=False)

    def list_keys(self) -> List[Dict[str, Any]]:
        return self._call("GET", "/auth/keys")

    def create_key(self, name: str, scopes: Optional[List[str]] = None,
                   tags: Optional[List[str]] = None,
                   expires_at: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name}
        if scopes:
            payload["scopes"] = scopes
        if tags:
            payload["tags"] = tags
        if expires_at:
            payload["expires_at"] = expires_at
        return self._call("POST", "/auth/keys", body=payload)

    def revoke_key(self, key_id: str) -> Dict[str, Any]:
        return self._call("DELETE", f"/auth/keys/{key_id}")

    def whoami(self) -> Dict[str, Any]:
        return self._call("GET", "/auth/me")

    def server_version(self) -> Dict[str, Any]:
        """The server's build identity ({version, commit}). Unauthenticated, so
        it works before login; a NotFound means the server predates the endpoint
        (an older build)."""
        return self._call("GET", "/version", require_auth=False)

    def change_password(self, current_password: str, new_password: str) -> Dict[str, Any]:
        return self._call("POST", "/auth/change-password",
                          body={"current_password": current_password,
                                "new_password": new_password})

    # -- the canonical observe door + the client-section sync door ----------
    def observe_field(self, resource: str, record_id: str, path: str, value: Any,
                      client: str, machine: str, unit: Optional[str] = None) -> Dict[str, Any]:
        body = {"path": path, "value": value, "client": client, "machine": machine}
        if unit is not None:
            body["unit"] = unit
        return self._call("POST", f"/{resource}/{record_id}/observe", body=body)

    def sync_client_section(self, resource: str, record_id: str, client: str, data: dict,
                            client_version: str = "",
                            client_item_id: Optional[str] = None) -> Dict[str, Any]:
        """The sync door: write only this client's own section. Physically
        cannot touch internal/canonical (the server rejects that)."""
        return self._call("PUT", f"/{resource}/{record_id}/clients/{client}", body={
            "client_version": client_version, "client_item_id": client_item_id, "data": data,
        })

    def upload_media(self, resource: str, record_id: str, *, data: bytes,
                     filename: str, role: str,
                     content_type: str = "application/octet-stream",
                     actor: Optional[str] = None) -> Dict[str, Any]:
        """Attach a media file (3D model, drawing, image) to a record's canonical
        media. Multipart upload (stdlib, no requests): the server stores the bytes
        content-addressed and stamps asserted:<actor> on the reference."""
        boundary = "----loobricMediaBoundary7MA4YWxkTrZu0gW"

        def _field(name: str, value: str) -> bytes:
            return (f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n").encode("utf-8")

        body = _field("role", role)
        if actor is not None:
            body += _field("actor", actor)
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8") + data + b"\r\n" + f"--{boundary}--\r\n".encode("utf-8")
        return self._send("POST", f"/{resource}/{record_id}/media", raw_body=body,
                          content_type=f"multipart/form-data; boundary={boundary}")

    # -- record creation (instance / catalog / entry) ------------------------
    def create_tool_record(self, **section) -> Dict[str, Any]:
        return self._call("POST", "/tool-instance-records", body=dict(section))

    def list_catalog_records(self) -> List[Dict[str, Any]]:
        return self._call("GET", "/tool-catalog-records").get("items", [])

    def get_catalog_record(self, record_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/tool-catalog-records/{record_id}")

    def create_catalog_record(self, source: str,
                              fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Seeded, atomic catalog-record create. `source` is the declared actor —
        the server stamps `asserted:<source>` on every field; the client never
        writes provenance. `fields` carries the nominal {value, unit} leaves
        (name/manufacturer/product_code + optional geometry/item_type)."""
        return self._call("POST", "/tool-catalog-records",
                          body={"actor": source, **(fields or {})})

    def create_instance_from_catalog(self, catalog_id: str,
                                     name: Optional[str] = None,
                                     qa: Optional[Dict[str, Any]] = None,
                                     cert: Optional[str] = None) -> Dict[str, Any]:
        """Create a new physical instance from a catalog type via the catalog->
        instance door. The server stamps the catalog_type_id link as
        asserted:<requester> and leaves the instance UNBOUND (a catalog is not a
        machine position). `name` overrides the copied catalog name when given.

        Optional manufacturer QA: `qa` is a geometry-shaped {value, unit} map and
        `cert` its certificate/serial; the server stamps each measured field
        observed:manufacturer@<serial> (the client never sends a raw source)."""
        body: Dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if qa is not None:
            body["qa"] = qa
        if cert is not None:
            body["cert"] = cert
        return self._call("POST",
                          f"/tool-catalog-records/{catalog_id}/create-instance",
                          body=body)

    def create_entry(self, machine_id: str, **section) -> Dict[str, Any]:
        return self._call("POST", "/tool-table-entry-records",
                          body={"machine_id": machine_id, **section})

    # -- users (admin) -------------------------------------------------------
    def list_users(self) -> Dict[str, Any]:
        """The admin account roster (admin-only). Returns {total, users}: the
        account count plus a per-account summary (email, role, flags, API-key
        count, created_at), newest first. No secrets — never a password hash or
        key material. A NotFound means the server predates the endpoint."""
        return self._call("GET", "/admin/users")

    def create_user(self, email: str, password: str, **extra) -> Dict[str, Any]:
        return self._call("POST", "/users",
                          body={"email": email, "password": password, **extra})

    def update_user(self, user_id: str, **fields) -> Dict[str, Any]:
        return self._call("PATCH", f"/users/{user_id}", body=dict(fields))

    def update_user_roles(self, user_id: str, **fields) -> Dict[str, Any]:
        return self._call("PATCH", f"/users/{user_id}/roles", body=dict(fields))

    # -- manufacturer catalogs ----------------------------------------------
    def list_catalogs(self) -> Any:
        return self._call("GET", "/catalogs")

    def get_catalog(self, catalog_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/catalogs/{catalog_id}")

    def catalog_analytics(self, catalog_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/catalogs/{catalog_id}/analytics")

    def create_catalog(self, **fields) -> Dict[str, Any]:
        return self._call("POST", "/catalogs", body=dict(fields))

    def update_catalog(self, catalog_id: str, **fields) -> Dict[str, Any]:
        return self._call("PATCH", f"/catalogs/{catalog_id}", body=dict(fields))

    # -- audit log -----------------------------------------------------------
    def query_audit_logs(self, operation: Optional[str] = None,
                         entity_type: Optional[str] = None,
                         entity_id: Optional[str] = None,
                         result: Optional[str] = None,
                         user_id: Optional[str] = None,
                         limit: Optional[int] = None,
                         offset: Optional[int] = None) -> Dict[str, Any]:
        """Query the audit log (who changed what, when). Regular accounts see
        their own rows; admins see all and may filter by user_id. Returns the
        server shape {logs, total_count, limit, offset, is_admin}; absent
        filters are omitted from the query string."""
        import urllib.parse
        params = {k: v for k, v in {
            "operation": operation, "entity_type": entity_type,
            "entity_id": entity_id, "result": result, "user_id": user_id,
            "limit": limit, "offset": offset,
        }.items() if v is not None}
        endpoint = "/audit-logs"
        if params:
            endpoint += "?" + urllib.parse.urlencode(params)
        return self._call("GET", endpoint)

    # -- change detection ----------------------------------------------------
    def changes_max_version(self, entity_type: str) -> Dict[str, Any]:
        return self._call("GET", f"/changes/{entity_type}/max-version")

    def changes_since_version(self, entity_type: str, version: int) -> Dict[str, Any]:
        return self._call(
            "GET", f"/changes/{entity_type}/since-version?since_version={version}")

    def changes_since_timestamp(self, entity_type: str, timestamp: str) -> Dict[str, Any]:
        return self._call(
            "GET", f"/changes/{entity_type}/since-timestamp?since_timestamp={timestamp}")

    # -- audit log -----------------------------------------------------------
    def list_audit_logs(self) -> Any:
        return self._call("GET", "/audit-logs")

    # -- backup (admin) ------------------------------------------------------
    def export_backup(self) -> Any:
        return self._call("GET", "/backup/export")

    def import_backup(self, backup_json: str, filename: str = "backup.json") -> Any:
        """Restore from a backup JSON document. /backup/import is a multipart
        file upload, so build the body by hand (stdlib, no requests)."""
        boundary = "----loobricFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/json\r\n\r\n"
            f"{backup_json}\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        return self._send("POST", "/backup/import", raw_body=body,
                          content_type=f"multipart/form-data; boundary={boundary}")

    # -- account -------------------------------------------------------------
    def reset_account(self) -> Dict[str, Any]:
        """Wipe all of the caller's tool data, keeping the account + keys."""
        return self._call("POST", "/account/reset", body={})

    # -- admin (factory reset) ----------------------------------------------
    def wipe_all(self, confirm: str) -> Dict[str, Any]:
        """FACTORY RESET (admin): delete ALL data, accounts, and API keys —
        including the calling admin. `confirm` must be the server's exact
        confirmation phrase or the server refuses with 400. There is no undo;
        afterwards the database is empty and the next registration becomes the
        new admin."""
        return self._call("POST", "/admin/wipe", body={"confirm": confirm})

