# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The hub, current: one command that always leaves you running the code you just wrote.

`npm run brain` from the panel's directory, or `.venv/bin/python dev.py` from here.

There are two ways to end up developing against a hub that is not your code, and this handles both.
The first is the hub that is still running from an hour ago -- the silent one, because it serves an
older shape of /ambient or /home, the panel renders it without complaint, and the result looks like
a panel bug. The second is what you get for noticing: you start a new one, the old one still holds
the port, and uvicorn says `[Errno 48] Address already in use`, which does not tell you which
process or what to do about it.

So this stops what is there, says what it stopped and how long it had been up, and starts a fresh
one with the reloader on. From then on every edit under hub/ restarts it by itself.

It will only ever stop a hub of OURS -- a python running this project's main.py or dev.py. Anything
else on the port is reported and left alone: on a machine running the brain from docker-compose,
the process holding 8300 is docker's proxy, and killing that would take out the container's
networking rather than the hub.
"""
import os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = os.environ.get("HUB_PORT", "8300")


def holders(port):
    """The pids listening on the port. `lsof` is everywhere a developer runs this; when it is not,
    the answer is an empty list and we simply try to bind, which is what would have happened anyway."""
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(p) for p in out.split()]


def about(pid):
    """(command, how long it has been up), or (None, None) if it has already gone.

    `-ww` is load-bearing: without it ps truncates the command to the terminal width, which on a
    normal window is about sixteen characters -- so every hub looked like `/opt/homebrew/Ce` and
    nothing was ever recognised as ours. And etime comes FIRST because it is the fixed-width half;
    with the command last there is nothing after it to confuse a split with."""
    try:
        r = subprocess.run(["ps", "-ww", "-o", "etime=,command=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None, None
    line = r.stdout.strip()
    if not line: return None, None
    etime, _, cmd = line.partition(" ")
    return cmd.strip(), etime.strip()


def ours(cmd):
    """One of this project's own hubs, rather than something else that happens to hold the port."""
    return bool(cmd) and "python" in cmd.lower() and re.search(r"\b(main|dev)\.py\b", cmd) is not None


def parent(pid):
    try:
        r = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def owner(pid):
    """The process to actually stop, walking up from whatever holds the port — or None if this is
    nobody's hub of ours.

    With the reloader on, a hub is TWO processes, and the one holding the port is the child, whose
    command line is `python -c from multiprocessing.spawn import spawn_main …`: it does not name
    main.py and never will. Judging that child on its own argv reads our own hub as a stranger and
    refuses to replace it. Its parent is the reloader, and stopping the parent takes the child with
    it, so the parent is the answer to both questions at once."""
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        cmd, up = about(pid)
        if cmd is None: return None
        if ours(cmd): return pid, cmd, up
        pid = parent(pid)
    return None


def stop(pid, cmd, up):
    print(f"replacing the hub on :{PORT} — pid {pid}, up {up}", flush=True)
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return True
    except PermissionError:
        print(f"  cannot stop pid {pid}: it belongs to another user", file=sys.stderr)
        return False
    for _ in range(40):                     # four seconds: uvicorn's reloader has children to take with it
        time.sleep(0.1)
        if not about(pid)[0]: return True
    print(f"  pid {pid} did not stop; leaving it alone", file=sys.stderr)
    return False


def main():
    # More than one pass, because a hub with the reloader on is two processes: stop the child and
    # the parent puts another one on the port before we have looked again. Stopping the parent takes
    # the child with it, but nothing promises which of them lsof lists first.
    for _ in range(3):
        rest = holders(PORT)
        if not rest: break
        for pid in rest:
            found = owner(pid)
            if found is None:
                cmd = about(pid)[0]
                if cmd is None:
                    continue                          # it went away while we were looking
                print(f"something that is not one of our hubs is on :{PORT} — pid {pid}: {cmd}\n"
                      f"stop it yourself, or run with HUB_PORT set to another port.", file=sys.stderr)
                return 1
            if not stop(*found):
                return 1
    else:
        print(f"something is still on :{PORT} after three tries; not starting another hub.", file=sys.stderr)
        return 1

    # main.py stays the one place that knows how to run the app; this only decides what runs before it
    env = {**os.environ, "HUB_RELOAD": "1"}
    return subprocess.call([sys.executable, str(HERE / "main.py")], cwd=HERE, env=env)


if __name__ == "__main__":
    sys.exit(main())
