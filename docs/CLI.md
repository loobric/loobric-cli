# loobric CLI

`loobric` is the command-line client for a Loobric Core server. Use it to create
a user, manage API keys, inspect machines, catalog records and tool records,
create tool instances, and review and resolve the binding inbox.

This page has two parts:

- [Command reference](#command-reference) — every subcommand, its arguments, and
  what it prints.
- [Walkthrough: from touch-off to a bound tool](#walkthrough-from-touch-off-to-a-bound-tool)
  — the core workflow, end to end.

For goal-oriented walkthroughs that span a CNC control and a CAM library, see
[Build a CAM tool set from your machine's tools](HOWTO_BUILD_CAM_SET_FROM_MACHINE.md)
and [Match a machine and a CAM tool set you built separately](HOWTO_MATCH_MACHINE_AND_CAM_TOOLS.md).

## Installing the command

Install from PyPI:

```bash
pip install loobric-cli
```

`loobric` is then on your PATH:

```bash
loobric --help
```

Without installing the console script you can run the module directly with
`python -m loobric.cli.main …`. Every command below works the same way;
only the leading word changes.

## Tab-completion (optional)

`loobric` can complete subcommands and flags in your shell. It uses
[`argcomplete`](https://github.com/kislyuk/argcomplete), which is **optional** —
the CLI stays stdlib-only and runs fine without it; completion just switches on
once it is installed and registered.

```bash
pip install "loobric-cli[completion]"     # or: pip install argcomplete
```

Then register it, **for the same command name you actually type**:

```bash
# Bash — per-shell (add to ~/.bashrc to make it permanent):
eval "$(register-python-argcomplete loobric)"        # the installed console script

# Zsh — ensure bashcompinit is loaded first, then the same eval:
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete loobric)"
```

Prefer global activation (completes every argcomplete-enabled script, once):

```bash
activate-global-python-argcomplete --user
```

Now `loobric create-cat<TAB>` completes to `create-catalog-record`,
`loobric create-record --<TAB>` lists `--from-catalog --name --qa --cert`, and
so on.

## How authentication works

`loobric` picks credentials in this order:

1. The `--api-key` flag, if given.
2. A saved session cookie from a previous `loobric login`.
3. No authentication — fine for `ping` and `register` (first user), rejected by
   everything else on a multi-tenant server.

A successful `login` saves the server URL and session cookie to
`~/.loobric/session.json` (owner-readable only). After that, you can omit
`--base-url` and run commands directly.

## Global options

These go before the subcommand: `loobric [global options] <command> [...]`.

| Option | Description |
| --- | --- |
| `--base-url URL`, `-b URL` | Server base URL. Defaults to `$LOOBRIC_BASE_URL`, then the saved session. |
| `--api-key KEY` | Authenticate with an API key instead of a session. Overrides the session cookie and `$LOOBRIC_API_KEY`. |
| `--verbose`, `-v` | Print the resolved base URL and auth source to stderr. |
| `--login` | Shortcut for interactive login (prompts for URL, email, password). |
| `--logout` | Shortcut to end the current session. |
| `-h`, `--help` | Show help. Works on the top level and on any subcommand. |

Environment variables:

- `LOOBRIC_BASE_URL` — default server URL.
- `LOOBRIC_API_KEY` — used **only** when you pass `--api-key "$LOOBRIC_API_KEY"`;
  it is not read automatically, to avoid clashing with a saved session.

## Command reference

Many commands resolve a machine, record, or tool set by its **id, its name, or
a unique id-prefix**: like a git short SHA, you can pass the first few characters
of an id as long as the prefix is unique, or pass the full name. An ambiguous
value prints the candidates and exits.

### Account and session

#### `register`

```
loobric --base-url URL register [email] [--password PASSWORD]
```

Create a user account. The first account on a fresh database becomes the admin;
later registrations require admin authentication. Prompts for any missing email
or password (with confirmation). Prints the created email and user id, then the
login command to run next.

#### `login`

```
loobric login [email] [--password PASSWORD] [--url URL]
```

Authenticate with email and password and save the session. Prompts for any
missing value; the URL prompt defaults to `http://127.0.0.1:8000`. On success,
prints the user and writes the session to `~/.loobric/session.json`.

#### `logout`

```
loobric logout
```

End the current session and delete the saved session file. `loobric --logout`
does the same thing.

#### `ping`

```
loobric ping
```

Check that the server is reachable and healthy (calls `/api/health`, no auth
required). Prints status, version (if reported), and the URL. Exits non-zero if
the server is unreachable or unhealthy.

#### `whoami`

```
loobric whoami
```

Show the authenticated account: email, role, admin flag, and id. This needs a
session (or an API key), so it reports "not authenticated" under solo mode,
which has no session.

### API keys

#### `create-key`

```
loobric create-key NAME [--scopes "read write"] [--tags "production mill-3"] [--expires-at ISO8601]
```

Create an API key. `--scopes` and `--tags` are space-separated lists;
`--expires-at` is an ISO 8601 datetime such as `2027-12-31T23:59:59Z`.

The plaintext key is printed to **stdout** on its own line; the human-readable
details and warnings go to **stderr**. This lets you capture just the key:

```bash
loobric create-key "LinuxCNC mill" --scopes "read write" > mill.key
```

The server stores only a hash of the key, so it cannot be shown again. Save it
when it is created.

#### `list-keys`

```
loobric list-keys
```

List your API keys: id, name, scopes, tags, and created / expiry / last-used
timestamps where available. The plaintext key is never shown.

#### `revoke-key`

```
loobric revoke-key KEY_ID
```

Revoke (delete) an API key by its id. Prints a confirmation.

### Machines and tools

#### `create-machine`

```
loobric create-machine NAME [--controller TYPE]
```

Create a machine and assert its name. `--controller` records the controller type
(e.g. `linuxcnc`). Prints the new machine's name and short id.

#### `list-machines`

```
loobric list-machines
```

List your machines: id, name, and controller type (when set).

#### `list-tools`

```
loobric list-tools
```

List your tool records — the public, machine-independent view of a tool
*instance*. Prints id, name, and a short geometry summary (shape and diameter)
when present. Instances are created with [`create-record`](#create-record),
either from a machine entry or from a [catalog record](#catalog-records).

#### `list-tool-sets`

```
loobric list-tool-sets
```

List your tool sets (named collections of tool records): id, name, member count,
last-updated, and version.

#### `tool-table`

```
loobric tool-table MACHINE
```

Show one machine's tool-table entries — the tools the controller has reported.
`MACHINE` is a machine id, name, or unique prefix. Each line shows the tool
number, description, diameter (when reported), and bind state: either `unbound`
or `bound -> <record-prefix>`.

#### `push`

```
loobric push MACHINE --entry "N[:DESC[:DIA]]" [--entry ...] [--client NAME] [--snapshot]
```

The controller-side tool-table sync: upsert tool-table entries on a machine by
tool number. `MACHINE` is a machine id, name, or unique prefix. Each `--entry`
is a tool number with an optional description and diameter (mm), e.g.
`--entry "3:1/4 downcut:6.35"`; the flag is repeatable. `--client` stamps the
client name on the push (default `loobric`). `--snapshot` makes the push
authoritative — entries absent from it are removed — and the removed tool
numbers are printed. Prints how many entries were pushed.

### Tool sets & setups

A tool set is a named collection of tool records — purely CAM-owned. Each
member's **number** is the CAM side's durable *claim* (the T-number posted
G-code will call); it is only ever changed by an assert, never overwritten by
the machine. A machine runs at most one set at a time as its **active setup**
(see `use-set`); `status` shows whether machine reality matches the active
set's claims. Loobric never gates anything — the flags inform, and resolution
happens through normal channels (mount, unload, edit the CAM library).

#### `create-set`

```
loobric create-set NAME
```

Create a tool set and assert its name. Prints the new set's name and short id.

#### `show-tool-set`

```
loobric show-tool-set SET
```

Show one tool set and its members. `SET` resolves by id, name, or unique prefix.
Lists each member ordered by number, showing the member's number and the
provenance `source` that vouches for it (`asserted`, `observed` when inherited
from a machine, or `unknown`), the tool it points at, and that tool's diameter.
`list-tool-sets` gives the across-the-shop overview (names + member counts); this
is the drill-in.

#### `add-to-set`

```
loobric add-to-set SET TOOL [TOOL ...] [--number N]
```

Add one or more tool records to a set. `SET` and each `TOOL` resolve by id,
name, or unique prefix. Existing members (and their numbers) are kept, and a
tool already in the set is skipped — membership is a set, not a bag.
`--number N` claims tool number `N` for the tool (exactly one `TOOL` in that
case): this is the durable CAM↔CNC contract that `status` checks the machine
against, and the number CAM should program. A member without a claim is
honestly unnumbered until one is asserted. Prints the tools added (and the
claim) and the resulting member count.

#### `remove-from-set`

```
loobric remove-from-set SET TOOL [TOOL ...]
```

Remove one or more tool records from a set; the rest are kept. `SET` and each
`TOOL` resolve by id, name, or unique prefix. Prints the tools removed and the
resulting member count.

> Both verbs are read-modify-write over the server's replace-only members door
> (`POST /tool-set-records/{id}/members`): they read current membership, apply
> the change, and write the full list back.

#### `use-set`

```
loobric use-set MACHINE SET
loobric use-set MACHINE --none
```

Make `SET` the machine's active setup — telling Loobric which tool set the
machine is being set up for. The previous setup (if any) ends automatically and
survives as history (`setup-history`). Activation changes **nothing** on either
side — no entry, no binding, no member, no number; it only changes what
`status` compares against. `--none` ends the active setup without a
replacement. Requires the `bind` scope: agent keys and bare controller sync
keys cannot switch setups.

#### `status`

```
loobric status MACHINE
```

The machine's setup view. The headline is **READY** when every claimed tool is
mounted, at the claimed number, with confirmed identity — the exact scope of
the word; it says nothing about offsets sanity or tool life. Otherwise
`NOT READY (n need attention, m notes)` with one line per claim:

```
millstone — bracket-job — NOT READY (2 need attention, 2 notes)

  T3   6mm endmill      ok
  T5   50mm face mill   blocked — T5 occupied by '20mm slot mill'
  T12  3mm drill        pending bind — mounted, confirm identity
  T14  90° chamfer      requested — not on machine
  ---- notes ----
  T30  touch probe      unlisted
  T8   —                unknown tool
```

Lines above the fold are unmet claims (important); **notes** are table rows the
set doesn't claim — real differences, informational only, never counted
against readiness. Nothing here is a task: pending lines are facts, fixed
through normal channels, except identity (`pending` / `resolve` / `bind`),
which is the one act only Loobric can record.

#### `setup-history`

```
loobric setup-history MACHINE
```

Which tool sets this machine ran, when, and their status — every `use-set` is
a durable row, never deleted.

### Catalog records

A **catalog record** is a manufacturer's nominal description of a tool *type* —
name, manufacturer, product code, and nominal geometry — independent of any
physical tool or machine position. Tool instances are created *from* a catalog
record (see [`create-record --from-catalog`](#create-record)), which links the
type without copying its values. Within an account the `(manufacturer,
product_code)` pair is unique: a second create with the same pair is rejected
with a 409 that names the existing record and invites reuse rather than a
duplicate.

#### `create-catalog-record`

```
loobric create-catalog-record [- | FILE] --source ACTOR [--file FILE]
                              [--name NAME] [--manufacturer MFR]
                              [--product-code CODE] [--diameter MM] [--flutes N]
```

Create a catalog record in one atomic, audited call. Nominal fields arrive as
JSON — on stdin (the `-` convention, the default when piped) or via `--file` —
with thin convenience flags for the by-hand case. `--source` is the **declared
actor** (e.g. `manufacturer:kennametal`); the server stamps `asserted:<source>`
on every field, so the client never writes provenance itself. `name`,
`manufacturer`, and `product_code` are required — the identity floor. The JSON
carries values and units only (never provenance):

```bash
# JSON on stdin, identity by flag:
echo '{"geometry": {"diameter": {"value": 6.35, "unit": "mm"}, "flutes": {"value": 2}}}' \
  | loobric create-catalog-record - --source manufacturer:kennametal \
      --name "1/4 downcut" --manufacturer Kennametal --product-code KC-0250

# entirely from flags:
loobric create-catalog-record --source manufacturer:kennametal \
    --name "1/4 downcut" --manufacturer Kennametal --product-code KC-0250 \
    --diameter 6.35 --flutes 2
```

Prints the new record's name and short id, noting the stamped source.

#### `list-catalog-records`

```
loobric list-catalog-records
```

List your catalog records: id, name, the `manufacturer  product_code` identity,
and nominal diameter when present.

#### `show-catalog-record`

```
loobric show-catalog-record CATALOG
```

Show one catalog record with **full provenance** — every canonical field (name,
manufacturer, product_code, item_type, and each geometry field) printed with its
value, unit, and the `source` that vouches for it. `CATALOG` resolves by id,
unique prefix, name, or product code.

### Importing from known formats

#### `import`

```
loobric import FILE [--dry-run] [--no-preserve] [--source ACTOR]
```

Import tool data from a known vendor format into catalog records. The format is
detected from the file (XML formats are told apart by their root element):
- **DIN 4000** — CSV and XML (ToolsUnited 2013 & 2016, incl. the decimal‑comma variant)
- **STEP P21** (`.p21`/`.stp`) — ISO 13399 cutting‑tool data
- **GTC package** (`.zip`) — ISO 13399, both GTC 2.x and the GTC 2017/ToolsUnited
  layout; also carries the tool's **3D models and images** as canonical media
- **SolidCAM** — its tool‑export XML (`<Results>`)
- **hyperMILL** — OPEN MIND `omtdx` XML

Each tool becomes a `ToolCatalogRecord` with the nominal geometry the format
states (diameter, shank diameter, length, flutes, depth of cut, and the shape its
class declares). For a GTC package, the 3D STEP models and images are uploaded as
the record's canonical media (viewable in the web UI). The server stamps
`asserted:<source>` on every field — the client writes no provenance. Fields the
format does not state are left `unknown`, never guessed. The full source payload
is preserved verbatim in the record's client section (disable with
`--no-preserve`).

Re‑importing the same catalog is safe: records that already exist (matched by the
`manufacturer` + `product_code` natural key) are reported as *skipped*, not
duplicated.

```
# See exactly what would be created, without sending anything:
loobric import 6767731.csv --dry-run

# Import a DIN 4000 export (a session/base URL must be configured):
loobric import 6767731.xml --source manufacturer:kennametal

# Import a GTC package — creates the record and uploads its 3D models + images:
loobric import 6676918.zip
```

`--dry-run` parses offline and prints the canonical fields per record. `--source`
overrides the default declared actor (`din4000-import`).

### Resolving the inbox

When a machine reports a tool the server does not recognize, the server may
propose a match. These proposals collect in the inbox.

#### `pending`

```
loobric pending
```

List inbox items awaiting review. For each: a short item id, the machine entry
(`T<n>`), the proposed matching record, and a confidence score with the reason.
This is an identity question — "is this the same tool?" — not a data conflict;
resolving it overwrites nothing on either side.

#### `resolve`

```
loobric resolve ITEM_ID {confirm|reject}
```

Resolve one inbox item. `ITEM_ID` is the item id or a unique prefix from
`pending`.

- `confirm` — "same tool": links the machine entry to the proposed record so
  future changes route between them. Both keep their data.
- `reject` — "different tools": drops the suggestion permanently. The entry stays
  unbound and keeps syncing.

If unsure, `reject`: a rejected pair can be linked manually later with `bind`,
while a wrong `confirm` is currently hard to undo.

### Managing bindings

A machine *entry* (a row in a tool table, `T<n>`) can be linked to a *tool
record*. Binding never overwrites either side; it just routes future changes
between them.

#### `bind`

```
loobric bind MACHINE TOOL_NUMBER RECORD
```

Link an entry to an existing tool record. `MACHINE` and `RECORD` accept an id,
name, or unique prefix; `TOOL_NUMBER` is the integer tool number (e.g. `3`).

#### `unbind`

```
loobric unbind MACHINE TOOL_NUMBER
```

Unbind an entry. The entry keeps its data and becomes eligible for future match
suggestions again.

#### `create-record`

```
loobric create-record MACHINE TOOL_NUMBER [--name NAME]
loobric create-record --from-catalog CATALOG [--name NAME] [--qa FILE --cert SERIAL]
```

Context-aware: it creates a tool instance from one of two sources, and the
outcome differs by bind state.

- **Entry form** (`MACHINE TOOL_NUMBER`): seed a brand-new instance from a
  machine entry's observed values and **bind** it to that tool-table position,
  in one step. Use this when the machine has a tool the server has never seen.
  `--name` defaults to the entry's description.
- **Catalog form** (`--from-catalog CATALOG`): create an instance from a
  [catalog record](#catalog-records) (resolved by id / unique prefix / name /
  product code) and leave it **unbound** — a catalog is a type, not a machine
  position. The new instance links the catalog via `catalog_type_id`; measured
  geometry and status stay unknown (nominal geometry is reachable through the
  link). `--name` defaults to the catalog record's name. Each call yields a new,
  distinct instance.

  Optional **manufacturer QA**: pass `--qa FILE` (a geometry-shaped JSON file —
  `{"diameter": {"value": …, "unit": …}, …}` — measured on the certified tool)
  together with `--cert SERIAL` (the certificate or serial those measurements are
  recorded against). The server stamps each measured field
  `observed:manufacturer@<serial>`, so a manufacturer's own measurements enter as
  observed values rather than nominal ones. The two flags are required together
  and are valid only on the catalog form.

The two forms are mutually exclusive — `--from-catalog` cannot be combined with
`MACHINE`/`TOOL_NUMBER`, and `--qa`/`--cert` are rejected on the entry form.

### Removing data

All three deletes prompt for confirmation. Pass `--yes`/`-y` to skip the prompt;
in a non-interactive shell (no TTY) `--yes` is required.

#### `delete-entry`

```
loobric delete-entry MACHINE TOOL_NUMBER [--yes]
```

Remove a machine-reported tool-table entry. If the controller reports it again,
it returns.

#### `delete-tool`

```
loobric delete-tool RECORD [--yes]
```

Delete a tool record. Any entries bound to it are unbound (not orphaned); their
data stays on the machine.

#### `delete-machine`

```
loobric delete-machine MACHINE [--yes]
```

Delete a machine and its tool-table entries. Tool records are not affected.

### The canonical assert door

#### `assert`

```
loobric assert RESOURCE RECORD_ID PATH VALUE
```

Set a canonical field directly — the canonical "assert" door. `RESOURCE` is a
record collection (e.g. `tool-set-records`, `machine-records`), `RECORD_ID` is
the record id, `PATH` is the canonical path (e.g. `name`), and `VALUE` is the
new value. `VALUE` is JSON-parsed when possible (so numbers, booleans, and JSON
objects work), otherwise it is treated as a plain string. For example:

```bash
loobric assert tool-set-records <id> name "Aluminum job"
```

### Admin and housekeeping

#### `audit`

```
loobric audit [--limit N]
```

Show recent audit-log entries — operation, entity type, short entity id, and
time, one per line. `--limit` caps how many are shown (default 50).

#### `reset`

```
loobric reset [--yes]
```

Wipe **all** tool data for the account — records, sets, machines, and
tool-table entries — keeping the login and API keys. Admin operation. Prompts
for confirmation; pass `--yes`/`-y` to skip it (required in a non-interactive
shell). Prints how many items were deleted.

#### `backup-export`

```
loobric backup-export [--out FILE]
```

Export a full account backup as JSON (admin). Writes to `--out FILE` when given,
otherwise to stdout.

#### `backup-import`

```
loobric backup-import FILE
```

Restore an account backup from a JSON file (admin). `FILE` is the path to a
backup produced by `backup-export`.

## Walkthrough: from touch-off to a bound tool

This is the core loop: a tool gets measured at the machine, shows up on the
server, and you decide what it is. It assumes you have a running server (see
[QUICK_START.md](QUICK_START.md)) and have logged in.

### 1. A tool is touched off at the machine

On the shop floor, an operator measures tool 3 and the controller's tool table
gets a new entry. A client such as
[loobric-linuxcnc](https://github.com/loobric/loobric-linuxcnc) syncs that entry
up to the server. Nothing for you to type here — this is the event that starts
the workflow.

### 2. See what the machine reported

```bash
loobric list-machines
loobric tool-table <machine>
```

The new entry shows up as `unbound`:

```
T3: 1/4" downcut  ⌀6.35  [unbound]
```

### 3. Check the inbox

If the server found a likely match for T3, it proposes one:

```bash
loobric pending
```

```
  ID: 4f2a1c9b
  Machine entry: T3
  Proposed match: 1/4 in downcut, 2-flute
  Confidence: 88% - same diameter and flute count
```

### 4. Resolve it

If the proposal is right, confirm it. T3 is now linked to that record:

```bash
loobric resolve 4f2a confirm
```

If it is wrong (or you are unsure), reject it. T3 stays unbound:

```bash
loobric resolve 4f2a reject
```

### 5. No proposal? Bind or create a record by hand

The inbox only holds cases the server could guess at. For an unbound entry with
no proposal, you have two choices.

If a matching record already exists, link to it:

```bash
loobric list-tools                 # find the record id
loobric bind <machine> 3 <record>
```

If no record exists yet, promote the entry into a new record in one step:

```bash
loobric create-record <machine> 3 --name "1/4 downcut"
```

### 6. Confirm the result

```bash
loobric tool-table <machine>
```

T3 now reads `bound -> <record>`. From here, changes on either side route
between the entry and the record. If you ever got it wrong, `unbind <machine> 3`
puts the entry back to `unbound` without losing its data.

## Using loobric-cli as a library

`loobric-cli` is MIT-licensed and importable. The same `Client` class the CLI
uses is the reference implementation other Python clients (FreeCAD, etc.) reuse,
so you don't have to write your own HTTP client:

```python
from loobric import Client, NotFound, LoobricClientError

c = Client(base_url="http://nas:8000", api_key="…")   # solo mode: api_key optional

for s in c.list_tool_sets():
    ...

c.create_machine("millstone", controller_type="linuxcnc")

try:
    c.get_machine(machine_id)
except NotFound:
    ...
```

Client methods return parsed data and raise `LoobricClientError` subclasses on
failure — `NotFound`, `AuthRequired`, `HTTPError`, and `ConnectionFailed` — so
callers handle errors instead of parsing printed output. The library is
stdlib-only, so `pip install loobric-cli` adds no third-party dependencies.
