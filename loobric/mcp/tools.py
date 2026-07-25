# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""SDK-independent tool registry for the Loobric MCP server.

Each tool is a ToolSpec: a name, an agent-facing description, a JSON Schema
for its input, and a plain handler ``(client, arguments) -> data``. The MCP
SDK wiring lives in ``main``; keeping handlers SDK-free lets the registry be
tested against a fake Client and reused by any future transport.

Vocabulary rule: names and descriptions are agent-facing surface — the agent
reads them to decide what to call — so they speak the public vocabulary
(UBIQUITOUS_LANGUAGE.md) and never the rejected terms (tested).

Assumptions:
- Writes go only through the create/assert doors; the server stamps
  provenance (lane discipline — the client never sends a raw source)
- The declared actor for every write is agent_actor() = "<agent>@mcp"
- assert_field refuses to overwrite a field whose current source kind is
  ``observed`` (ObservedValueError), enforced here because the server's
  assert door deliberately has no precedence rule (humans may correct bad
  measurements; agents may not overwrite them)
"""
import os
import posixpath
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

AGENT_ENV = "LOOBRIC_MCP_AGENT"


def agent_actor() -> str:
    """The provenance actor for MCP-mediated writes: ``<agent>@mcp``.

    The who is the agent product name from LOOBRIC_MCP_AGENT (default
    "agent"); the where is the fixed channel. Mirrors the CLI's own
    ``human@cli``. Read at call time so hosts can set it per-connection.
    """
    who = (os.getenv(AGENT_ENV) or "agent").strip() or "agent"
    return f"{who}@mcp"


class ObservedValueError(Exception):
    """An assert targeted a field whose current value is machine-measured
    (source kind ``observed``). Refused: measured values outrank agent
    assertions on this channel. A human may still override via the CLI or
    Web UI."""


class MediaDownloadError(Exception):
    """A media fetch was refused (non-http(s) URL) or failed (size cap,
    network). Raised before anything reaches the Loobric Server."""


# attach_media_from_url: which records carry canonical media, the roles the
# server's MediaRef contract accepts, and the download cap.
_MEDIA_RESOURCES = ("tool-catalog-records", "tool-instance-records")
_MEDIA_ROLES = ("model_3d", "model_3d_basic", "drawing_2d", "image", "icon",
                "logo", "document")
MEDIA_MAX_BYTES = 50 * 1024 * 1024


def _download_media(url: str, max_bytes: int = MEDIA_MAX_BYTES) -> Tuple[bytes, str]:
    """Fetch `url` and return (bytes, content_type).

    http(s) only — the MCP server must never read local files into records.
    The request carries the transport's User-Agent (rebranded loobric-mcp/…
    by main): default Python UAs are Cloudflare-403'd (error 1010), and many
    manufacturer sites do the same. Reads at most max_bytes + 1 so an
    oversized file fails fast instead of filling memory."""
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise MediaDownloadError(
            "refusing to fetch %r — only http(s) URLs are allowed" % url)
    from loobric import transport                 # call-time UA read
    req = Request(url, headers={"User-Agent": transport.USER_AGENT})
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read(max_bytes + 1)
            content_type = (resp.headers.get_content_type()
                            or "application/octet-stream")
    except MediaDownloadError:
        raise
    except OSError as exc:
        raise MediaDownloadError("download failed: %s" % exc) from exc
    if len(data) > max_bytes:
        raise MediaDownloadError(
            "download exceeds the %d MB cap" % (max_bytes // (1024 * 1024)))
    return data, content_type


def _create_catalog_record(client: Any, args: Dict[str, Any]) -> Any:
    """Create with the agent actor; if `client_data` is sent without a
    `client` name, inject client='mcp' — the server stores client_data only
    under a named client section and silently drops it otherwise."""
    fields = dict(args["fields"])
    if fields.get("client_data") and not fields.get("client"):
        fields["client"] = "mcp"
    return client.create_catalog_record(source=agent_actor(), fields=fields)


def _attach_media(client: Any, args: Dict[str, Any]) -> Any:
    data, content_type = _download_media(args["url"])
    filename = (args.get("filename")
                or posixpath.basename(urlsplit(args["url"]).path)
                or "download")
    return client.upload_media(
        args["resource"], args["record_id"], data=data, filename=filename,
        role=args["role"],
        content_type=args.get("content_type") or content_type,
        actor=agent_actor())


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Any, Dict[str, Any]], Any]


def _schema(properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


_RECORD_ID = {"record_id": {"type": "string",
                            "description": "The record's id (internal.id)."}}

# Resources the assert door serves, mapped to the Client getter the observed
# guard uses to inspect the current field before asserting.
_ASSERTABLE_RESOURCES: Dict[str, str] = {
    "tool-instance-records": "get_tool_record",
    "tool-catalog-records": "get_catalog_record",
    "tool-set-records": "get_tool_set",
    "machine-records": "get_machine",
    "tool-table-entry-records": "get_entry",
}


def _current_source(record: Dict[str, Any], path: str):
    """The provenance source string at a dotted canonical path, or None."""
    node = record.get("canonical") or {}
    for segment in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(segment)
        if node is None:
            return None
    if isinstance(node, dict):
        return node.get("source")
    return None


# -- handlers ----------------------------------------------------------------

def _assert_field(client, args):
    resource = args["resource"]
    getter = _ASSERTABLE_RESOURCES.get(resource)
    if getter is None:
        raise ValueError(f"Unknown resource {resource!r}; one of "
                         f"{sorted(_ASSERTABLE_RESOURCES)}")
    record = getattr(client, getter)(args["record_id"])
    source = _current_source(record, args["path"])
    if source and str(source).startswith("observed"):
        raise ObservedValueError(
            f"Refusing to assert over {args['path']!r}: its current value is "
            f"machine-measured ({source}). Measured values outrank agent "
            "assertions. Tell the user — a human can override via the CLI or "
            "Web UI if the measurement really is wrong.")
    return client.assert_field(resource, args["record_id"], args["path"],
                               args["value"], actor=agent_actor())


def _query_audit_logs(client, args):
    allowed = ("operation", "entity_type", "entity_id", "result", "user_id",
               "limit", "offset")
    return client.query_audit_logs(**{k: args[k] for k in allowed if k in args})


TOOLS: List[ToolSpec] = [
    # -- reads ---------------------------------------------------------------
    ToolSpec(
        "list_tool_instance_records",
        "List the account's tool instance records — each one physical tool "
        "with canonical identity/geometry/status and per-field provenance.",
        _schema({}, []),
        lambda c, a: c.list_tool_records()),
    ToolSpec(
        "get_tool_instance_record",
        "Get one tool instance record, including every canonical field's "
        "provenance source (observed / asserted / derived / unknown).",
        _schema(dict(_RECORD_ID), ["record_id"]),
        lambda c, a: c.get_tool_record(a["record_id"])),
    ToolSpec(
        "list_tool_catalog_records",
        "List tool catalog records — reusable catalog-level types (nominal "
        "geometry, manufacturer, product code), independent of physical tools.",
        _schema({}, []),
        lambda c, a: c.list_catalog_records()),
    ToolSpec(
        "get_tool_catalog_record",
        "Get one tool catalog record by id.",
        _schema(dict(_RECORD_ID), ["record_id"]),
        lambda c, a: c.get_catalog_record(a["record_id"])),
    ToolSpec(
        "list_tool_sets",
        "List ToolSets — named collections of tools, optionally linked to a "
        "Machine (member numbers then come from its tool table).",
        _schema({}, []),
        lambda c, a: c.list_tool_sets()),
    ToolSpec(
        "get_tool_set",
        "Get one ToolSet with its members and their derived states "
        "(loaded / requested / pending bind).",
        _schema(dict(_RECORD_ID), ["record_id"]),
        lambda c, a: c.get_tool_set(a["record_id"])),
    ToolSpec(
        "list_machines",
        "List the account's Machines (CNC machines/controllers).",
        _schema({}, []),
        lambda c, a: c.list_machines()),
    ToolSpec(
        "get_machine",
        "Get one Machine record by id.",
        _schema(dict(_RECORD_ID), ["record_id"]),
        lambda c, a: c.get_machine(a["record_id"])),
    ToolSpec(
        "list_tool_table_entries",
        "List tool table entries — the machine side of the CAM-to-CNC "
        "contract (tool_number, offsets, bound tool instance). Optionally "
        "filter by machine_id.",
        _schema({"machine_id": {"type": "string",
                                "description": "Limit to one Machine."}}, []),
        lambda c, a: c.list_entries(a.get("machine_id"))),
    ToolSpec(
        "list_inbox",
        "List Inbox items awaiting a human: proposed bindings and frozen "
        "conflicts. Read-only here — confirmation happens in the Web UI, "
        "never through an agent.",
        _schema({}, []),
        lambda c, a: c.list_inbox()),
    ToolSpec(
        "get_changes",
        "List changes to an entity type since a version number — what "
        "changed since the last look.",
        _schema({"entity_type": {"type": "string",
                                 "description": "e.g. tool_instance_record"},
                 "since_version": {"type": "integer"}},
                ["entity_type", "since_version"]),
        lambda c, a: c.changes_since_version(a["entity_type"],
                                             a["since_version"])),
    ToolSpec(
        "query_audit_logs",
        "Query the audit log: who changed what, when, with what result. "
        "Filters: operation (CREATE/UPDATE/ASSERT/...), entity_type, "
        "entity_id, result, limit, offset.",
        _schema({"operation": {"type": "string"},
                 "entity_type": {"type": "string"},
                 "entity_id": {"type": "string"},
                 "result": {"type": "string"},
                 "user_id": {"type": "string"},
                 "limit": {"type": "integer"},
                 "offset": {"type": "integer"}}, []),
        _query_audit_logs),
    ToolSpec(
        "whoami",
        "The authenticated account and server build — say which account and "
        "server you are acting on before writing anything.",
        _schema({}, []),
        lambda c, a: {"user": c.whoami(), "server": c.server_version()}),
    # -- writes (create/assert doors only) -----------------------------------
    ToolSpec(
        "create_catalog_record",
        "Author a tool catalog record in one atomic, audited act. `fields` "
        "carries {value[, unit]} leaves. Identity floor (required, top "
        "level): name, manufacturer, product_code — use manufacturer 'shop' "
        "for a shop-made tool. ALL dimensional/spec data goes inside the "
        "nested `geometry` object, never at the top level (the server "
        "rejects unknown top-level keys). Canonical geometry keys: diameter, "
        "cutting_diameter, shape, length, flutes, cutting_edge_height, "
        "shank_diameter, gauge_length; extra geometry keys are accepted as "
        "{value[, unit]} leaves. Non-geometry data the source states — "
        "grade, coating, substrate, source URL, availability, alternate "
        "part numbers — belongs in the free-form `client_data` dict: store "
        "it there, never cram it into the name string and never discard it. "
        "Leave what the source does not state absent; never invent values. "
        "The server stamps every field asserted:<agent>@mcp.",
        _schema({"fields": {
            "type": "object",
            "description": "Request fields, e.g. "
                           "{\"name\": {\"value\": \"1/4in 4-flute endmill\"},"
                           " \"manufacturer\": {\"value\": \"Kennametal\"},"
                           " \"product_code\": {\"value\": \"H1TE4SE0250\"},"
                           " \"geometry\": {\"flutes\": {\"value\": 4},"
                           " \"cutting_diameter\": {\"value\": 0.25,"
                           " \"unit\": \"in\"}},"
                           " \"client_data\": {\"grade\": \"KCPM15\","
                           " \"source_url\": \"https://…\"}}."}},
            ["fields"]),
        _create_catalog_record),
    ToolSpec(
        "create_instance_from_catalog",
        "Create a new physical tool instance from a catalog record. The "
        "instance starts unbound with status unknown; `name` overrides the "
        "copied catalog name.",
        _schema({"catalog_id": {"type": "string"},
                 "name": {"type": "string"}}, ["catalog_id"]),
        lambda c, a: c.create_instance_from_catalog(a["catalog_id"],
                                                    name=a.get("name"))),
    ToolSpec(
        "create_tool_set",
        "Create a ToolSet, optionally named.",
        _schema({"name": {"type": "string"}}, []),
        lambda c, a: c.create_tool_set(name=a.get("name"),
                                       actor=agent_actor())),
    ToolSpec(
        "add_to_tool_set",
        "Add tool instance records to a ToolSet by id.",
        _schema({"set_id": {"type": "string"},
                 "tool_record_ids": {"type": "array",
                                     "items": {"type": "string"}}},
                ["set_id", "tool_record_ids"]),
        lambda c, a: c.add_to_set(a["set_id"], a["tool_record_ids"])),
    ToolSpec(
        "remove_from_tool_set",
        "Remove tool instance records from a ToolSet by id.",
        _schema({"set_id": {"type": "string"},
                 "tool_record_ids": {"type": "array",
                                     "items": {"type": "string"}}},
                ["set_id", "tool_record_ids"]),
        lambda c, a: c.remove_from_set(a["set_id"], a["tool_record_ids"])),
    ToolSpec(
        "link_tool_set_to_machine",
        "Link a ToolSet to a Machine; member numbers are then inherited from "
        "the machine's tool table entries.",
        _schema({"set_id": {"type": "string"},
                 "machine_id": {"type": "string"}},
                ["set_id", "machine_id"]),
        lambda c, a: c.link_set_to_machine(a["set_id"], a["machine_id"])),
    ToolSpec(
        "attach_media_from_url",
        "Attach a media file to a record's canonical media by downloading "
        "it from a public http(s) URL — a 3D model (STEP), 2D drawing, "
        "product photo, or datasheet from a manufacturer page. When a "
        "product page offers a CAD download, fetching the model is part of "
        "storing everything the manufacturer supplies. The MCP server "
        "fetches the bytes (50 MB cap) and uploads them through the audited "
        "media door; the server stamps the reference asserted:<agent>@mcp. "
        "Re-attaching identical bytes for the same role is a no-op; no "
        "removal tool exists — dropping a media reference is a human action "
        "in the Web UI.",
        _schema({"resource": {"type": "string",
                              "enum": list(_MEDIA_RESOURCES)},
                 "record_id": {"type": "string"},
                 "url": {"type": "string",
                         "description": "Public http(s) URL of the file."},
                 "role": {"type": "string", "enum": list(_MEDIA_ROLES),
                          "description": "What the file is: model_3d / "
                                         "model_3d_basic (3D solid, e.g. "
                                         "STEP), drawing_2d, image (product "
                                         "photo), icon, logo, document "
                                         "(datasheet or other)."},
                 "filename": {"type": "string",
                              "description": "Stored filename; defaults to "
                                             "the URL's basename."},
                 "content_type": {"type": "string",
                                  "description": "MIME type; defaults to "
                                                 "the response header."}},
                ["resource", "record_id", "url", "role"]),
        _attach_media),
    ToolSpec(
        "assert_field",
        "Deliberately declare a canonical value on a record (the audited "
        "assert door); stamped asserted:<agent>@mcp. REFUSED if the field's "
        "current value is machine-measured (observed) — measured values "
        "outrank agent assertions; a human can override via the CLI or Web "
        "UI. Resources: tool-instance-records, tool-catalog-records, "
        "tool-set-records, machine-records, tool-table-entry-records.",
        _schema({"resource": {"type": "string",
                              "enum": sorted(_ASSERTABLE_RESOURCES)},
                 "record_id": {"type": "string"},
                 "path": {"type": "string",
                          "description": "Dotted canonical path, e.g. "
                                         "'name' or 'geometry.diameter'."},
                 "value": {"description": "The value to declare."}},
                ["resource", "record_id", "path", "value"]),
        _assert_field),
]

TOOLS_BY_NAME: Dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def call_tool(client, name: str, arguments: Dict[str, Any]) -> Any:
    """Dispatch one tool call to its handler. Raises KeyError for an unknown
    tool; handler exceptions (including ObservedValueError) propagate for the
    transport layer to surface."""
    return TOOLS_BY_NAME[name].handler(client, arguments or {})
