# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""MCP resources: condensed domain documentation served to agents.

Agents that read these before acting make far better tool calls — the
vocabulary and the three-doors model are not guessable. These are CONDENSED
COPIES; the sources of truth are loobric-server's docs/UBIQUITOUS_LANGUAGE.md
and docs/CONCEPTS.md. When those change materially, update these.
"""

GLOSSARY_MD = """\
# Loobric vocabulary (condensed — for agents)

- **ToolInstanceRecord** — one *physical* tool: canonical identity/geometry/
  status plus per-client sections. Two identical end mills are two instances.
- **ToolCatalogRecord** — a catalog-level *type*: manufacturer, product code,
  *nominal* geometry. A ToolInstanceRecord may reference one. "Catalog record"
  is the row; "catalog" alone means a collection of them.
- **ToolTableEntry** — one machine's tool-table row: `tool_number` (the only
  identifier that travels in G-code — the CAM-to-CNC contract), offsets, and
  optionally a bound instance.
- **Machine** — a CNC machine/controller, first-class.
- **ToolSet** — a named collection of tools; when *linked* to a Machine its
  member numbers are inherited from the machine's tool table. Member states:
  `loaded` (bound and in sync), `requested` (awaiting the operator),
  `pending bind` (mounted, binding unconfirmed).
- **Binding / bind / bound** — the confirmed link between a ToolTableEntry and
  a ToolInstanceRecord. Server-proposed, HUMAN-confirmed (in the Inbox/Web
  UI); agents never confirm bindings.
- **Inbox** — items awaiting a human: proposed bindings, frozen conflicts.
- **Pocket** — the magazine position a tool occupies; an implementation
  detail, never identity.

## Provenance
Every canonical leaf is `{value, source}`. Source kinds:
- `observed` — a machine measured it (e.g. `observed:linuxcnc@mill01`)
- `asserted` — a human/client declared it (e.g. `asserted:human@cli`,
  `asserted:claude@mcp`)
- `derived` — computed from other canonical fields
- `unknown` — nobody stated it; the value is null, honestly

Agent rule (permanent): **agents assert, never observe** — `observed`
requires a deterministic pipeline from measurement to value; an LLM in the
loop means assert. Asserts over an `observed` value are refused on this
channel.
"""

CONCEPTS_MD = """\
# Loobric concepts (condensed — for agents)

## The contract
The tool number (`T3 M6`) is the single point of contact between what CAM
assumed and what the machine holds. If the CAM side and the machine side
describe tool 3 differently, parts get scrapped and spindles crash. Loobric
records both sides' number-to-tool mappings and makes their agreement a
verifiable fact. Surfacing a disagreement to the user is the single most
valuable thing an agent can do here.

## The three doors
Canonical data changes ONLY through:
1. **sync** — a client writes its own `clients.<name>` section (routine;
   physically cannot touch canonical)
2. **observe** — a machine reports a measured value (NOT available to agents)
3. **assert** — an explicit, audited declaration with a named actor

Everything an agent writes goes through create/assert doors and is stamped
`asserted:<agent>@mcp` by the server — attributed, audited, and ranked below
measured values on this channel.

## "Tools" is ambiguous — disambiguate before answering
A tool-table ENTRY (machine-observed row: number + offsets, possibly
unbound) is not a tool INSTANCE record (a physical tool in the crib). A
fresh controller sync produces entries and nothing else, so "no tool records
+ N unbound entries" is a normal starting state. Asked "what tools do I
have?" when the records list is empty, report BOTH facts and ask which the
user meant — never answer a bare "none" while a machine is reporting a
populated table.

## Catalog records: store everything, in its right place
A manufacturer page usually states more than the identity floor. Put
dimensional spec in the nested `geometry` object ({value[, unit]} leaves;
canonical keys include flutes, cutting_diameter, shank_diameter; extra keys
are accepted) — never at the top level, where unknown keys are rejected.
Everything else the source states — grade, coating, substrate, source URL,
availability, alternate part numbers — goes in the free-form `client_data`
dict. Nothing the manufacturer states gets discarded or crammed into the
name string; and a field the source does NOT state stays absent — an honest
blank beats a confident guess.

## What agents cannot do (by design, permanently)
- delete anything, or reset/re-seed an account
- confirm or reject Inbox items (binding stays a human act)
- write through the observe door
- overwrite a machine-measured (`observed`) value via assert

When one of these blocks you, say so and point the user at the Web UI or CLI
— do not look for a workaround.

## Credential hygiene (if you can bind, something is misconfigured)
These limits are properties of the AGENT KEY (`read sync assert`), not of
you. If the MCP server is down and you fall back to the `loobric` CLI, the
CLI may pick up a HUMAN session file or a broader key — and suddenly binds,
deletes, or setup switches will succeed. Succeeding is the failure: you are
holding a person's credential. Check `loobric whoami` before writing, prefer
LOOBRIC_API_KEY with the agent preset, and if a write that should be beyond
you succeeds, stop and tell the user their agent environment is carrying the
wrong credential.
"""

RESOURCES = [
    {"uri": "loobric://glossary", "name": "glossary",
     "description": "Loobric domain vocabulary, condensed for agents.",
     "mimeType": "text/markdown", "text": GLOSSARY_MD},
    {"uri": "loobric://concepts", "name": "concepts",
     "description": "The tool-number contract, the three doors, and the "
                    "agent rules.",
     "mimeType": "text/markdown", "text": CONCEPTS_MD},
]
