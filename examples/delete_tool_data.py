#!/usr/bin/env python3
# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Delete every machine, tool record, and tool set in the caller's account —
keeping API keys, login, AND catalog records.

The narrower sibling of `loobric reset --yes` (which also removes catalog
records). Useful for demo accounts: clear the working data, keep the keys the
clients are configured with and the catalog you imported.

Auth comes from the saved CLI session (run `loobric login` first) or
LOOBRIC_BASE_URL / LOOBRIC_API_KEY. A key needs the `bind` and `delete`
doors; a login session needs nothing special.

    python examples/delete_tool_data.py           # show counts, ask first
    python examples/delete_tool_data.py --yes     # no prompt
    python examples/delete_tool_data.py --dry-run # show what would go

Order matters: active setups are ended first (a deleted set must not stay
some machine's active setup), then sets, then machines (their entries go with
them), then tool records.
"""
import argparse
import os
import sys

# Prefer the adjacent repo source over whatever `loobric` an installed
# site-packages happens to hold — a stale install predating the setups verbs
# fails here with AttributeError('list_setups') otherwise.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loobric import Client, transport
from loobric.errors import LoobricClientError

if not hasattr(Client, "list_setups"):
    import loobric
    sys.exit("This script needs loobric-cli >= 1.4.0; the interpreter loaded "
             "an older 'loobric' package from %s" % os.path.dirname(loobric.__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", "-y", action="store_true",
                    help="skip the confirmation prompt")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be deleted; delete nothing")
    args = ap.parse_args()

    transport.load_session()
    c = Client()

    machines = c.list_machines()
    tools = c.list_tool_records()
    sets = c.list_tool_sets()
    try:
        setups = c.list_setups(status="active")
    except LoobricClientError:
        setups = []                      # pre-setups server: nothing to end

    def name(rec, key="name"):
        v = ((rec.get("canonical") or {}).get(key) or {}).get("value")
        return v or rec["internal"]["id"][:8]

    print("Account tool data on %s:" % (c.base_url or transport.BASE_URL))
    print("  %d machine(s): %s" % (len(machines),
                                   ", ".join(name(m) for m in machines) or "-"))
    print("  %d tool set(s): %s" % (len(sets),
                                    ", ".join(name(s) for s in sets) or "-"))
    print("  %d tool record(s)" % len(tools))
    print("  (%d active setup(s) will be ended first)" % len(setups))
    print("Kept: API keys, login, catalog records.")

    if args.dry_run:
        print("Dry run - nothing deleted.")
        return 0
    if not (machines or tools or sets):
        print("Nothing to delete.")
        return 0
    if not args.yes:
        if input("Delete all of the above? [y/N]: ").strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 1

    for row in setups:
        c.end_setup(row["id"])
    for s in sets:
        c.delete_tool_set(s["internal"]["id"])
    for m in machines:                   # entries go with their machine
        c.delete_machine(m["internal"]["id"])
    for t in tools:
        c.delete_tool_record(t["internal"]["id"])

    print("Deleted %d machine(s), %d tool set(s), %d tool record(s)."
          % (len(machines), len(sets), len(tools)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LoobricClientError as e:
        print("Error: %s" % e, file=sys.stderr)
        sys.exit(1)
