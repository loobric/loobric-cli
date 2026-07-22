# ADR 0001 — Extract the client into `loobric-cli`

**Status:** Accepted (2026-06-22) · **Supersedes:** the single-file `loobric.py` shipped in `loobric-core`.

## Context

`loobric.py` had grown to ~2,100 LOC as a single stdlib-only file inside the
`loobric-core` (server) repo: transport + an importable `Client` library + the
full CLI, all in one module. It was also hand-vendored (a drifting copy) into
`loobric-freecad`. Format importers (loobric-core#31 — DIN4000, GTC, P21, TDM,
Zoller, SolidCAM, HyperMill) would add thousands of lines and **heavy
third-party dependencies** (XML/CSV/SQLite parsers), which must never burden the
lean client or the server. The single file was the wrong unit of organization,
and shipping the client from the server repo conflated two concerns.

## Decisions

1. **Dedicated repository** — the client moves out of `loobric-core` into its own
   repo, `loobric-cli`. Runtime depends on nothing from the server (it only
   speaks the public REST API). `loobric-core` keeps its reference-client role via
   a dev/test dependency for integration tests.
2. **Naming** — distribution **`loobric-cli`**, import package **`loobric`**,
   CLI command **`loobric`**. "Loobric" is the organization, not an application, so
   application surfaces drop it. The import package is `loobric` (not
   `loobric`) deliberately: `loobric-core` already owns the `loobric` import name and
   the two co-exist when the server dev-depends on the client.
3. **Distribution via PyPI with extras** — `pip install loobric-cli` (stdlib
   only) for library + CLI; `pip install loobric-cli[importers]` pulls the heavy
   parser deps used only by the importer subpackage.
4. **FreeCAD consumes the package via pip** (confirmed supported for addons) —
   no more hand-vendored copy.
5. **MIT license** retained (the server is AGPL-3.0; an MIT client can be reused
   freely).

### Other user-facing renames (loobric → loobric)

- session dir `~/.loobric` → `~/.loobric`; env `LOOBRIC_BASE_URL` → `LOOBRIC_BASE_URL`;
  error base class `LoobricError` → `LoobricClientError`.

## Target layout

```
loobric/
  __init__.py        # exports Client + errors          (stdlib only)
  errors.py          # typed exceptions                 (stdlib only)
  transport.py       # urllib HTTP + session state       (stdlib only)
  client.py          # Client: one method per endpoint    (stdlib only)
  cli/               # argparse + commands + formatting   (stdlib only)
  importers/         # format parsers — OPT-IN, heavy deps live ONLY here
```

Organizing principle: **`transport` + `client` stay stdlib-only forever.** `cli`
depends on `client`; `importers` depend on `client` (parse a file → emit records
→ push through existing `Client` methods). Each importer is one module behind a
registry; per principle 6, each ships a matching exporter and preserves unknown
keys (lossless round-trip).

## Migration sequence

1. **This ADR + repo scaffold + lean core** (errors/transport/client) extracted
   and import-verified. ✅
2. **Port the CLI** into `loobric/cli/` (argparse, commands, resolvers,
   formatting); preserve the call-time transport hook so `monkeypatch`ing
   `loobric.transport.make_request` still intercepts. Port the CLI tests.
3. **Packaging + CI + PyPI publish**; activate the `loobric` console script.
4. **Re-point consumers:** `loobric-core` → dev dependency for integration tests;
   `loobric-freecad` → pip dependency; remove `loobric.py` from `loobric-core`.
5. **Then** build importers (loobric-core#31) behind the `[importers]` extra.

Do not start step 5 before 1–2 land.
