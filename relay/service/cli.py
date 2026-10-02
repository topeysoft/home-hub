# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The operator's hands, until payments do this: carry a house, stop carrying it, see who is here.

On the relay box it runs inside the service's own container, against the same file:

    ssh root@<relay> docker exec relay-service python cli.py list
    ssh root@<relay> docker exec relay-service python cli.py grant temi 2027-10-01 "Temi, by hand"
    ssh root@<relay> docker exec relay-service python cli.py stop temi
    ssh root@<relay> docker exec relay-service python cli.py rotate temi     # a house that lost its key
    ssh root@<relay> docker exec relay-service python cli.py release temi    # the name goes back

Granting is the only one with a consequence a household would notice the same minute: a house that
was refused at login is carried the next time its frpc retries, which it does on its own.
"""
import os, sys, time
from datetime import UTC, datetime
from pathlib import Path

from registry import Registry

USAGE = "usage: cli.py list | grant <name> <YYYY-MM-DD> [note] | stop <name> | rotate <name> | release <name>"


def when(ts):
    if ts is None: return "-"
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def run(argv: list[str], registry: Registry, out=print) -> int:
    if not argv: out(USAGE); return 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "list":
            for h in registry.houses():
                state = "carried until " + when(h["entitled_until"]) if h["entitled_until"] else "held until " + when(h["held_until"])
                out(f"{h['name']:<30} {state:<26} {h['note']}")
            return 0
        if cmd == "grant" and len(args) >= 2:
            until = datetime.strptime(args[1], "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
            registry.grant(args[0], until, " ".join(args[2:]))
            out(f"{args[0]} is carried until {args[1]}.")
            return 0
        if cmd == "stop" and len(args) == 1:
            registry.grant(args[0], time.time() - 1, "stopped by hand")
            out(f"{args[0]} keeps its name and is not carried. Its open tunnel lasts until it next reconnects.")
            return 0
        if cmd == "rotate" and len(args) == 1:
            out(registry.rotate(args[0]))
            return 0
        if cmd == "release" and len(args) == 1:
            registry.release(args[0])
            out(f"{args[0]} is free for anyone again.")
            return 0
    except LookupError as e:
        out(f"No house called {e.args[0]}."); return 1
    except ValueError as e:
        out(str(e)); return 2
    out(USAGE)
    return 2


if __name__ == "__main__":
    data = Path(os.environ.get("RELAY_DATA", "/data"))
    sys.exit(run(sys.argv[1:], Registry(data / "houses.db", zone=os.environ.get("RELAY_ZONE", "elyir.app"))))
