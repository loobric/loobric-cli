# Changelog

All notable changes to **loobric-cli** (the Loobric client library + `loobric` CLI)
are recorded here. This project adheres to [Semantic Versioning](https://semver.org/).

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
