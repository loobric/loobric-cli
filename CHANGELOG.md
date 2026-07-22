# Changelog

All notable changes to **loobric-cli** (the Loobric client library + `loobric` CLI)
are recorded here. This project adheres to [Semantic Versioning](https://semver.org/).

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
