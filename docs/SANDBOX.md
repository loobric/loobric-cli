# Try the Loobric sandbox

The sandbox is a free, shared Loobric server at **`https://api.loobric.com`**.
It lets you exercise the whole tool-data loop — the `loobric` CLI, the FreeCAD
addon, and the LinuxCNC client — without installing a server of your own.

> ⚠️ **It's a playground, not storage.** The sandbox is shared and may be reset
> at any time; data and accounts can be removed without notice. Keep nothing
> real here. For anything you care about, [self-host](https://github.com/loobric/loobric-core)
> — it's the same Docker image, free and AGPL-3.0.

## 1. Install the client

```bash
pip install loobric-cli
```

Library + `loobric` CLI, standard-library only, no dependencies.

## 2. Point at the sandbox

Set this once and every command targets the sandbox — no `--base-url` needed:

```bash
export LOOBRIC_BASE_URL=https://api.loobric.com
loobric ping        # confirm the server is reachable
```

## 3. Create an account

```bash
loobric register you@example.com
```

You'll be prompted for a password (or pass `--password`). Registration is open —
no invite code.

## 4. Get an API key (do this — don't rely on the login session)

The sandbox stores login sessions **in memory**, so they're dropped whenever the
server restarts or redeploys. **API keys persist**, so the moment-to-moment
sandbox experience is much loobricer with a key. Log in once to mint one:

```bash
loobric login you@example.com
loobric create-key sandbox --scopes "read write"
export LOOBRIC_API_KEY=<the key it prints>
```

With `LOOBRIC_API_KEY` exported, the client authenticates with the key on every
call (it takes precedence over the session cookie), so you keep working across
redeploys. If a `loobric` command ever says you're not authenticated even though
you logged in, that's the session expiring — the API key avoids it.

## 5. Do something interesting

Grab the seed script and run it:

```bash
curl -O https://raw.githubusercontent.com/loobric/loobric-cli/master/examples/quickstart.sh
bash quickstart.sh
```

[`quickstart.sh`](https://github.com/loobric/loobric-cli/blob/master/examples/quickstart.sh)
is just a readable list of `loobric` commands — **open it in your editor** to see
exactly what it does and to learn how to script the CLI yourself. It seeds a
small demo catalog (a handful of endmills, drills, a V-bit, a face mill — across
two plausible manufacturers) and walks the whole loop:

1. creates a demo machine (`sandbox-mill`),
2. seeds the catalog,
3. turns a couple of catalog entries into physical **tool instances**,
4. collects them in a **tool set**, and
5. pushes a machine **tool table** (as a stand-in controller).

It's meant for a fresh account. Then explore what it built:

```bash
loobric list-catalog-records          # the seeded catalog
loobric list-tools                    # your physical instances
loobric show-tool-set "Sandbox demo set"
loobric show-machine sandbox-mill     # its tool table + linked sets
loobric pending                       # binding proposals awaiting review
loobric audit --limit 20              # the full provenance trail
```

Every field carries its **source** (who asserted or observed it) — that
provenance is the point of Loobric, and `show-*`/`audit` make it visible.

You can also import a real vendor export instead of the demo seed:

```bash
loobric import your-tools.csv --dry-run    # DIN 4000, STEP P21, GTC, SolidCAM, hyperMILL
```

## 6. Optional: the FreeCAD and LinuxCNC clients

Both clients can target the same sandbox account using the API key from step 4.

- **FreeCAD** — install the [loobric-freecad](https://github.com/loobric/loobric-freecad)
  addon, open its preferences, confirm the server URL is
  `https://api.loobric.com`, and paste your API key. Its README has a
  "Try against the sandbox" section.
- **LinuxCNC** — the single-file [loobric-linuxcnc](https://github.com/loobric/loobric-linuxcnc)
  client reads its server from the environment:

  ```bash
  export LOOBRIC_API_URL=https://api.loobric.com
  export LOOBRIC_API_KEY=<your sandbox key>
  ```

## Reset or clean up

```bash
loobric reset --yes              # wipe YOUR tool data (keeps your login + keys)
loobric revoke-key <id>          # revoke a key you created
loobric change-password          # change your password (prompts for current + new)
```

### Admin: factory-reset the whole sandbox

The sandbox admin can wipe **everything** — all data, all accounts, and all API
keys, including the admin's own — back to an empty server. The next account to
register then becomes the new admin.

```bash
loobric wipe-all                 # prompts for the confirmation phrase
# non-interactive:
loobric wipe-all --confirm "WIPE ALL DATA AND ACCOUNTS"
```

There is no undo.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Base URL required` | `export LOOBRIC_BASE_URL=https://api.loobric.com` |
| `401` / "not authenticated" after a while | Your session expired — use the API key (step 4) |
| `409` on import or seed | That record already exists (matched by natural key) — not an error |
