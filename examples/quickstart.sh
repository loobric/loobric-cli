#!/usr/bin/env bash
#
# quickstart.sh — seed a Loobric account with a small demo, and learn to script
# the `loobric` CLI by reading it.
#
# This is nothing but a list of ordinary `loobric` commands. Read it top to
# bottom to see how the pieces fit together; run it to give a fresh account
# (e.g. the hosted sandbox) something to explore.
#
# ---------------------------------------------------------------------------
# Prerequisites (see docs/SANDBOX.md):
#
#   pip install loobric-cli
#   export LOOBRIC_BASE_URL=https://api.loobric.com
#   loobric register you@example.com
#   loobric login    you@example.com
#   loobric create-key sandbox --scopes "read write"
#   export LOOBRIC_API_KEY=<the key it printed>     # the CLI reads this automatically
#
# Then run:   bash quickstart.sh
# ---------------------------------------------------------------------------
#
# Meant for a FRESH account. It's safe to re-run — the catalog records dedupe on
# their natural key (a re-run just reports them as already present) — but a
# re-run does create another demo machine and tool set. Wipe first with
# `loobric reset --yes` if you want a clean slate.

# Read no command's stdin from this script, so `cat quickstart.sh | bash` can't
# accidentally feed the script text into a command. Every value below is a flag.
exec < /dev/null

# Fail fast with a clear message if the environment isn't set up. `list-machines`
# is a cheap authenticated call — it works with either a session or an API key,
# so it's a reliable "am I signed in?" probe.
: "${LOOBRIC_BASE_URL:?Set the server first, e.g. export LOOBRIC_BASE_URL=https://api.loobric.com}"
if ! loobric list-machines >/dev/null 2>&1; then
  echo "Not signed in, or the server is unreachable." >&2
  echo "Create and export an API key first — see the header of this file." >&2
  exit 1
fi

echo "== Seeding ${LOOBRIC_BASE_URL} =="

echo
echo "== 1. A machine to bind tools against =="
loobric create-machine sandbox-mill --controller linuxcnc

echo
echo "== 2. A small catalog, across two manufacturers =="
# create-catalog-record needs an identity (name + manufacturer + product-code);
# --source is the actor the server stamps on every field as 'asserted:<source>'.
loobric create-catalog-record --source manufacturer:kennametal \
  --name "1/4in 2-flute flat endmill" --manufacturer Kennametal \
  --product-code B201 --diameter 6.35 --flutes 2
loobric create-catalog-record --source manufacturer:kennametal \
  --name "1/8in 2-flute flat endmill" --manufacturer Kennametal \
  --product-code B101 --diameter 3.175 --flutes 2
loobric create-catalog-record --source manufacturer:kennametal \
  --name "6mm 3-flute endmill" --manufacturer Kennametal \
  --product-code B306 --diameter 6.0 --flutes 3
loobric create-catalog-record --source manufacturer:kennametal \
  --name "5mm jobber drill" --manufacturer Kennametal \
  --product-code D050 --diameter 5.0
loobric create-catalog-record --source manufacturer:sandvik \
  --name "60deg V-bit engraver" --manufacturer Sandvik \
  --product-code V160 --diameter 6.0
loobric create-catalog-record --source manufacturer:sandvik \
  --name "90deg chamfer mill" --manufacturer Sandvik \
  --product-code C290 --diameter 6.0
loobric create-catalog-record --source manufacturer:sandvik \
  --name "3mm ball-nose endmill" --manufacturer Sandvik \
  --product-code BN030 --diameter 3.0 --flutes 2
loobric create-catalog-record --source manufacturer:sandvik \
  --name "50mm face mill" --manufacturer Sandvik \
  --product-code F500 --diameter 50.0 --flutes 5

echo
echo "== 3. Turn a couple of catalog entries into physical tools =="
# --from-catalog resolves by product code; the new instance is UNBOUND (not on
# any machine yet) and carries the catalog's nominal geometry.
loobric create-record --from-catalog B201 --name "1/4in endmill (stock)"
loobric create-record --from-catalog V160 --name "60deg V-bit (stock)"

echo
echo "== 4. Collect them in a tool set =="
loobric create-set "Sandbox demo set"
loobric add-to-set "Sandbox demo set" "1/4in endmill (stock)" "60deg V-bit (stock)"

echo
echo "== 5. Push a machine tool table (as a stand-in controller) =="
# Each --entry is N[:description[:diameter]]. This is the controller side of the
# loop; the server may then propose binding these entries to the tools above.
loobric push sandbox-mill --client linuxcnc-sim \
  --entry "1:1/4 downcut:6.35" --entry "2:60 vee:6.0"

echo
echo "== Done. Now explore what you built: =="
echo "  loobric list-catalog-records              # the seeded catalog"
echo "  loobric list-tools                        # your physical instances"
echo "  loobric show-tool-set \"Sandbox demo set\""
echo "  loobric show-machine sandbox-mill         # its tool table + linked sets"
echo "  loobric pending                           # binding proposals to review"
echo "  loobric audit --limit 20                  # the full provenance trail"
