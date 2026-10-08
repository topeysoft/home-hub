# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The operator's hands, until payments do this: carry a house, stop carrying it, see who is here.

On the relay box it runs inside the service's own container, against the same file:

    ssh root@<relay> docker exec relay-service python cli.py list
    ssh root@<relay> docker exec relay-service python cli.py grant jordan 2027-10-01 "Jordan, by hand"
    ssh root@<relay> docker exec relay-service python cli.py stop jordan
    ssh root@<relay> docker exec relay-service python cli.py rotate jordan     # a house that lost its key
    ssh root@<relay> docker exec relay-service python cli.py release jordan    # the name goes back
    ssh root@<relay> docker exec relay-service python cli.py invite 2027-10-05 "a tester, by hand"
    ssh root@<relay> docker exec relay-service python cli.py invites
    ssh root@<relay> docker exec relay-service python cli.py uninvite 9HTF   # an unused code, by its last four

An invite is a grant made before anybody claims: the house that brings the code -- when it claims its
name, or any time after -- is carried until the date, without anybody running grant. Each works once
and is no good after 30 days. The code is shown once; the relay keeps only its hash.

Granting is the only one with a consequence a household would notice the same minute: a house that
was refused at login is carried the next time its frpc retries, which it does on its own.
"""
import os, sys, time
from datetime import UTC, datetime
from pathlib import Path

from registry import Registry

USAGE = ("usage: cli.py list | grant <name> <YYYY-MM-DD> [note] | stop <name> | rotate <name> | release <name>\n"
         "       | invite <YYYY-MM-DD> [note] | invites | uninvite <last four>")


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
        if cmd == "invite" and len(args) >= 1:
            until = datetime.strptime(args[0], "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
            if until <= time.time(): out("That date has passed."); return 2
            code = registry.invite(until, " ".join(args[1:]))
            out(code)
            out(f"Carries whoever brings it until {args[0]}. Works once, for 30 days; this is the only time it is shown.")
            return 0
        if cmd == "invites":
            for i in registry.invites():
                state = (f"used by {i['used_by']} {when(i['used_at'])}" if i["used_by"]
                         else "ran out " + when(i["use_by"]) if i["use_by"] < time.time() else "unused, good until " + when(i["use_by"]))
                out(f"…{i['hint']}  carries until {when(i['until'])}  {state:<34} {i['note']}")
            return 0
        if cmd == "uninvite" and len(args) == 1:
            try: registry.uninvite(args[0])
            except LookupError: out(f"No unused code ends in {args[0]}."); return 1
            out(f"The code ending in {args[0].upper()} carries nobody now.")
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
