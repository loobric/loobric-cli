# Changelog

All notable changes to **loobric-cli** (the Loobric client library + `loobric` CLI)
are recorded here. This project adheres to [Semantic Versioning](https://semver.org/).

## [1.6.0] — 2026-08-16

### Added
- **Cutting data presets** (server ≥ 0.13.0; loobric-server
  `docs/PRESETS.md`, grilled 2026-08-16): `Client.contribute_preset()` /
  `Client.list_presets()` for the audited contribution door — an F&S
  recommendation with a source, engineering values only, replace-own on
  `(origin, label)`. Two new MCP tools, **`contribute_preset`** and
  **`list_presets`** (23 tools total): the contribute description teaches
  the doctrine — origin is the recommender, the agent is stamped as
  transcriber, raw feed/RPM are never stored, and replace-own is the
  agent's only revision path (removal stays a human act; there is
  deliberately no preset delete tool).

## [1.5.0] — 2026-08-01

### Added
- **`Client.key_info()` — credential introspection** (server ≥ 0.8.0,
  loobric-server #44): what may the presented key actually do? Returns the
  key's audit identity (`channel` + `api_key_id`), name, **effective** door
  scopes, and explicit `read_only` / `legacy` flags — needs nothing beyond a
  valid credential, so a read-only key can learn it is read-only without
  provoking a 403. `loobric whoami` now shows the block when authed with an
  API key ("Key: … / Scopes: read — read-only", with the legacy degradation
  called out and its fix named). Older servers: the block is simply absent.

## [1.4.1] — 2026-07-30 (lessons from the first setups-era field sessions)

### Fixed
- **`loobric-mcp` crashed at startup on a fresh install** — the MCP Python
  SDK released 2.0.0, which removes the 1.x low-level `Server` decorator API
  (`AttributeError: 'Server' object has no attribute 'list_tools'`), and the
  `[mcp]` extra was unbounded (`mcp>=1.0`), so new installs pulled the
  incompatible SDK while old environments kept working. Pinned to
  `mcp>=1.0,<2`, plus a startup guard that names the one-line fix
  (`pip install 'mcp>=1.0,<2'`) instead of a bare traceback for environments
  that already hold 2.x. SDK 2.0 support is a separate port.
- **"What tools do I have?" on a fresh sync no longer reads as "none"**
  (first setups-era demo session, 2026-07-30). A controller push creates
  tool-table entries with no tool records behind them, and both surfaces
  answered ambiguously: `loobric list-tools` with an empty crib now names
  each machine's entry count and the disambiguating verbs; the MCP
  `list_tool_instance_records` description teaches agents to report BOTH
  facts and ask which the user meant; `loobric://concepts` gains the
  entry-vs-record distinction.
- MCP `list_tool_sets` / `get_tool_set` descriptions caught up with 1.4.0's
  setups vocabulary (claims + derived states; the retired "linked"/"loaded"
  language was still there).

### Added
- **Credential hygiene, taught where it's breached** (same demo session: the
  agent's CLI fallback picked up a human session and bound five entries —
  "agents never bind" is a credential property, and the credential was
  wrong). `loobric://concepts` gains a "if you can bind, something is
  misconfigured" section (check `loobric whoami`, prefer the agent-preset
  key, report an over-privileged success as the failure it is); the README
  gains an "AI agents (MCP) & credential hygiene" section — the MCP server's
  first README documentation — telling humans to give agent workstations an
  agent-preset key and never a shared session file.
- MCP `machine_setup_status` now states the exact CLI verb shape
  (`loobric use-set MACHINE SET`, `--none` to end; no `--machine` flag) so
  agents relay it correctly instead of guessing.
- **`loobric delete-key KEY [--yes]`** — permanently remove a **revoked**
  key's row (resolves by id/name/prefix; refuses an active key — revoke
  first, deliberately two steps). Library: `Client.delete_key`. Pairs with
  loobric-server's `DELETE /auth/keys/{id}?purge=true`.

## [1.4.0] — 2026-07-29 (BREAKING: pairs with loobric-server 0.7.0)

### Added
- **Setups** (MAPPING_PLAN.md): `loobric use-set MACHINE SET` makes a tool set
  the machine's active setup (`--none` ends it); `loobric status MACHINE`
  renders the ratified view — `READY` / `NOT READY (n need attention, m
  notes)` with per-line states (`ok`, `requested`, `mismounted`, `blocked`,
  `pending bind`; notes: `unlisted`, `unknown tool`); `loobric setup-history
  MACHINE` lists the machine's setup rows. Client library: `use_set`,
  `end_setup`, `list_setups`, `active_setup`, `reconciliation`.
- **`add-to-set --number N`** — claim a tool number for a member (the durable
  CAM↔CNC contract `status` checks the machine against). Client
  `add_to_set(..., numbers={id: n})`.
- MCP: `machine_setup_status` (read-only setup view) and `numbers` on
  `add_to_tool_set`. Switching setups stays beyond agent keys (bind door).
- **Units on the assert door.** `loobric assert … --unit rpm` and an optional
  `unit` argument on the MCP `assert_field` tool / `LoobricClient.assert_field`,
  for the new server-side machine capability fields (`spindle.max_rpm`,
  `spindle.power`, …) where a bare number is ambiguous.
- **`loobric show machine` prints spindle/coolant capability** sections with
  per-field provenance when present.

### Removed (BREAKING)
- `loobric link-machine` and `Client.link_set_to_machine` — the set↔machine
  link is no longer a set field; use `use-set`. The MCP
  `link_tool_set_to_machine` tool is gone for the same reason (and agents
  could not hold the new verb's door anyway).

## [1.3.1] — 2026-07-27

### Fixed
- **`loobric-mcp` now diagnoses a dead credential at startup.** Three of the
  first four real field sessions failed on a rejected key (HTTP 401 on every
  call), and the startup check silently swallowed it — the agent could only
  report "everything 401s" mid-task. A 401 at connect time now prints one
  specific stderr message naming the causes in likelihood order: host not
  restarted after a key change (env is read at startup only), a
  project-scoped MCP config entry shadowing the global one, a
  key/LOOBRIC_BASE_URL server mismatch, or a revoked key. Non-401 errors
  stay quiet — a down server surfaces properly on the first tool call.

## [1.3.0] — 2026-07-27

Companion to loobric-server **0.6.0**, which enforces door-aligned API key
scopes (`read sync observe assert bind delete admin`) and degrades pre-0.6.0
keys to read-only. **Rotate old keys** — this release makes that one word.

### Added
- **`loobric create-key --preset agent|controller|cam|full`** — named scope
  presets for the door model. `agent` (the AI/MCP key) is
  `read sync assert`: it can never observe, bind, or delete, making the
  agent doctrine a property of the credential. `--scopes` still wins when
  both are given; no preset grants `admin`.
- **`loobric-mcp` least-privilege startup warning**: on connect it
  introspects its key (`/auth/me` now reports effective scopes on 0.6.0+)
  and logs one line when the key grants doors the MCP server never uses —
  warn, don't refuse. Quiet against older servers and solo mode.

## [1.2.0] — 2026-07-25

### Added
- **MCP: `attach_media_from_url` — agents can now attach media** (founder
  decision reversing the v1 exclusion, prompted by the first real-world
  session leaving a manufacturer's CAD model behind). The MCP server
  downloads a public **http(s)** URL (50 MB cap; carries the loobric-mcp
  User-Agent — default Python UAs are Cloudflare-403'd) and uploads the
  bytes through the existing audited media door onto a catalog or instance
  record's canonical media, stamped `asserted:<agent>@mcp`. Roles:
  `model_3d`, `model_3d_basic`, `drawing_2d`, `image`, `icon`, `logo`,
  `document`. File bytes never enter the model's context; non-http(s) URLs
  (`file://`, …) are refused before any fetch; re-attaching identical bytes
  is a no-op; **no removal tool exists** — dropping a media reference stays
  a human action. Tool count: 21.

### Fixed
- **MCP: `client_data` no longer silently lost on create.** The server
  stores `client_data` only under a named client section; the 1.1.1 guidance
  told agents to send it but nothing named the client, so the data was
  dropped without error (caught by the media e2e smoke). The
  `create_catalog_record` handler now injects `client: "mcp"` when
  `client_data` arrives unnamed; an explicitly named client is left alone.

## [1.1.1] — 2026-07-25

### Fixed
- **MCP: `create_catalog_record` now teaches field placement.** The first
  real-world agent session sent spec fields at the top level (`flute_count`,
  `hand_of_cut`), was correctly rejected by the server's lane discipline, and
  fell back to cramming the data into the name string. The tool description
  and input-schema example now document the nested `geometry` object, the
  canonical key names (`flutes`, not `flute_count`; extra geometry keys
  accepted), and that non-geometry manufacturer data (grade, coating,
  substrate, source URL, availability, alternate part numbers) belongs in the
  free-form `client_data` dict — stored, never discarded. The
  `loobric://concepts` resource gains the same guidance ("store everything,
  in its right place"). No behavior change — the server accepted all of this
  all along; the agent just couldn't discover it.

## [1.1.0] — 2026-07-25

### Added
- **The Loobric MCP server (`loobric-mcp`).** A stdio MCP server that lets AI
  agents on any MCP host (Claude Code, Claude Desktop, …) read and write tool
  data on a Loobric Server through the public API's audited doors. Install
  with `pip install 'loobric-cli[mcp]'` (the base package stays stdlib-only).
  Configure with `LOOBRIC_BASE_URL`, `LOOBRIC_API_KEY` (omit for solo mode),
  and `LOOBRIC_MCP_AGENT` (the agent name for provenance, default `agent`).
  The locked rules (see the project's `MCP_PLAN.md`):
  - every agent write is stamped **`asserted:<agent>@mcp`** — attributed, audited
  - **agents assert, never observe** — no observe-door tool exists
  - **no deletes, no Inbox confirmation, no bind/unbind, no credential
    management** — those tools simply don't exist
  - the **observed guard**: an assert targeting a field whose current value is
    machine-measured (`observed`) is refused before any request is made
  - 20 tools plus two agent-facing resources (`loobric://glossary`,
    `loobric://concepts`) that teach the domain vocabulary
- **`Client.query_audit_logs()`** — the audit-log query verb
  (`GET /api/v1/audit-logs` with operation/entity/result filters), added to
  the reference client first per the standing rule; the MCP
  `query_audit_logs` tool uses it.

> Note: the git tag `v1.0.0` (2026-07-24) contains this same MCP work, but the
> `loobric-cli` **1.0.0 published on PyPI** (2026-07-22) predates it and is the
> rename-only release below — it has no `loobric.mcp` package and no `[mcp]`
> extra. PyPI versions are immutable, so the MCP server first *ships* as 1.1.0.

### Fixed
- **Explicit `User-Agent` on every request** (`loobric-cli/<version>`;
  `loobric-mcp/<version>` from the MCP entry point). Cloudflare rejects
  default Python UAs in front of api.loobric.com (error 1010 — the
  smooth-linuxcnc incident); this closes that loose end for all consumers of
  the transport. Overridable via `extra_headers`.

## [1.0.0] — 2026-07-22

The first release under the **Loobric** name (package `loobric-cli`, import
`loobric`, CLI `loobric` — the former "Smooth" branding is retired). Renaming
only; functionally equivalent to 0.5.1.

## [0.5.1] — 2026-06-29

### Added
- **`loobric list-users`** — the admin account roster (and `Client.list_users()`
  library method). Lists how many accounts exist and who they are (email, role,
  flags, API-key count, created date), newest first, over loobric-core's
  `GET /api/v1/admin/users`. Admin-only on the server; an older server with no
  such endpoint reports it plainly instead of erroring. No secrets are shown —
  never a password hash or key material. Needs loobric-core ≥ 0.3.5.

## [0.5.0] — 2026-06-27

### Added
- **`loobric version`** — print this client's version and the server's build,
  with **no login required** (the server build comes from the unauthenticated
  `/version` endpoint). The quickest "are my client and server compatible / is
  my deploy current?" check. Works even with no server configured (shows the
  client version alone). Previously the server build was only visible via
  `loobric whoami`, which requires authentication.
- **`loobric change-password`** — change the authenticated user's password
  (prompts for the current and new password, or takes `--current`/`--new`).
  Wraps the existing `POST /auth/change-password` endpoint, which had no CLI verb.
- **`loobric wipe-all`** — ADMIN factory reset: delete ALL data, ALL accounts, and
  ALL API keys on the server, **including the calling admin**. Guarded by an exact
  typed (or `--confirm`ed) phrase; there is no undo. After it runs the server is
  empty and the next registration becomes the new admin. Requires
  loobric-core ≥ 0.3.2 (new `POST /api/v1/admin/wipe` endpoint).
  Distinct from `loobric reset`, which wipes only your tool data and keeps accounts.

## [0.4.0] — 2026-06-26

### Added
- **`examples/quickstart.sh`** — a readable shell script of plain `loobric`
  commands that seeds an account with a small demo (a handful of endmills,
  drills, a V-bit, a face mill, across two plausible manufacturers) and walks
  the whole loop: machine → catalog → instance → tool set → tool-table push.
  Run it to populate a fresh or sandbox account; read it to learn how to script
  the CLI. (No new `loobric` subcommand — it's just the commands you'd type.)
- **`docs/SANDBOX.md`** — an API-key-first walkthrough for the free hosted
  sandbox at `https://api.loobric.com`.

### Changed
- **`LOOBRIC_API_KEY` is now read from the environment automatically.** Export it
  once (as `create-key` already advises) and every command authenticates with
  the key — no need to repeat `--api-key`. Precedence is `--api-key` flag >
  `LOOBRIC_API_KEY` env > saved session cookie. This is the right default for the
  sandbox, where login sessions are dropped on each server redeploy but API keys
  persist.
- **`loobric register` now pins the server it ran against** (saves `base_url` to
  `~/.loobric/session.json`), so the next command targets the same server without
  re-passing `--base-url`.
- The "Base URL required" error now names the one-liner to fix it
  (`export LOOBRIC_BASE_URL=…`).

## [0.3.0] — 2026-06-23

### Added
- **`show-machine`, `show-tool`, `show-key`** — every listable entity now has a
  matching show verb (full list/show symmetry). Each resolves by id, name, or
  unique prefix. `show-tool` prints a tool instance with full provenance;
  `show-machine` adds its tool-table summary and linked sets; `show-key` resolves
  one API key.

## [0.2.0] — 2026-06-22

### Added
- **`loobric import` — tool-data importers.** One command auto-detects the format
  and turns a vendor export into catalog records on the server. Supported:
  - **DIN 4000** — CSV and XML (ToolsUnited 2013 & 2016 editions, incl. the
    decimal-comma variant).
  - **STEP P21** (ISO 13399) — identity and geometry read from the inline ISO
    13399 mnemonics; no property dictionary required.
  - **GTC packages** (`.zip`, ISO 13399) — both GTC 2.x and the GTC 2017 /
    ToolsUnited inner-zip layout. The tool's 3D STEP models and images are
    uploaded as canonical media on servers whose media backend is enabled.
  - **SolidCAM** (`<Results>` XML) and **hyperMILL** (OPEN MIND `omtdx` XML).
  - `--dry-run` previews exactly what would be created without sending anything;
    `--no-preserve` skips storing the raw source payload.
- **`Client.upload_media()`** — attach a file (3D model, drawing, image) to a
  record's canonical media (stdlib multipart).
- Importers are an opt-in subpackage (`loobric.importers`) with a public
  `parse()` entry point returning `CatalogRecordDraft`s.

### Design
- Every importer is **standard-library only** — the package stays vendorable and
  runs in constrained interpreters. The `[importers]` extra is reserved for
  future formats that need heavier parsers; no bundled importer requires it.
- Imports never fabricate: a field the source does not state stays `unknown`
  (`shape` comes only from a source-declared class/type, never inferred), the
  server stamps `asserted:<source>` provenance, the raw payload is preserved
  verbatim, and a re-imported catalog is skipped via its natural key, not
  duplicated.

## [0.1.0]

### Added
- Initial extraction of the Loobric client from the single-file `loobric.py`: the
  importable `loobric.Client` library and the `loobric` CLI, plus PyPI
  packaging (Trusted Publishing) and CI.
