#!/usr/bin/env python3
"""Saying something about releases right now, without cutting another one.

A release manifest is signed once and never changes, which is right for "what is v0.3.1" and useless
for "do not install v0.3.1, we got it wrong". This publishes the other thing: one small signed file,
replaced in seconds, that hubs check against the same keys.

    tools/channel.py show                 what hubs are being told
    tools/channel.py hold v0.3.1          stop it reaching anybody who has not taken it
    tools/channel.py unhold v0.3.1        let it go again
    tools/channel.py out v0.3.2 0.1       let a tenth of houses take it by themselves
    tools/channel.py out v0.3.2 1         ...and then the rest

It may only ever slow a hub down. There is deliberately no way to say "install this version": a file
that could name a release could name an old one, and a downgrade is the one thing a signature over a
release cannot protect a house from. Withholding is all it does, so the worst a forged or replayed
one can do is stop updates -- which hubs treat as a reason to ignore it, not to obey it.

`hold` also stops a person tapping Install, on purpose: the maker saying a release is broken is worth
more than a household's guess that it might be fine.
"""
import json, os, subprocess, sys, time, urllib.error, urllib.request

RELEASES = os.environ.get("HOME_HUB_RELEASES") or "https://github.com/topeysoft/home-hub/releases/download"
URL = f"{RELEASES}/channel/channel.json"
PRIV = os.environ.get("HOME_HUB_RELEASE_KEY") or os.path.expanduser("~/.home-hub/release-key.pem")
KEYS = "driver-layer/host/release-keys.d"
TAG = "channel"


def current() -> dict:
    """What hubs are being told now. A missing one is not an error; it is the ordinary state."""
    try:
        with urllib.request.urlopen(URL, timeout=30) as r: return json.loads(r.read())
    except (urllib.error.URLError, ValueError): return {"schema": 1, "hold": [], "rollout": {}}


def write(doc: dict) -> str:
    """One version to a line, because the host reads the hold list with sed in a shell script."""
    doc = {"schema": 1, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "hold": sorted(set(doc.get("hold") or [])), "rollout": doc.get("rollout") or {}}
    return json.dumps(doc, indent=2) + "\n"


def sign_and_publish(text: str):
    open("channel.json", "w").write(text)
    subprocess.run(("openssl", "pkeyutl", "-sign", "-inkey", PRIV, "-rawin",
                    "-in", "channel.json", "-out", "channel.json.sig"), check=True)
    # Never hand out a signature that checks against none of the keys hubs hold: it would be ignored
    # in the field and look exactly like a hold that worked.
    if not any(subprocess.run(("openssl", "pkeyutl", "-verify", "-pubin", "-inkey", os.path.join(KEYS, k),
                               "-rawin", "-in", "channel.json", "-sigfile", "channel.json.sig"),
                              capture_output=True).returncode == 0
               for k in sorted(os.listdir(KEYS)) if k.endswith(".pub")):
        raise SystemExit(f"That signature checks against none of the keys in {KEYS}. No hub would read it.")
    if subprocess.run(("gh", "release", "view", TAG), capture_output=True).returncode != 0:
        subprocess.run(("gh", "release", "create", TAG, "--title", "What the maker is saying about releases",
                        "--notes", "Not a release. Hubs read the signed file attached here to learn which "
                                   "releases are being held back and how far a new one has been let out."),
                       check=True)
    subprocess.run(("gh", "release", "upload", TAG, "channel.json", "channel.json.sig", "--clobber"), check=True)
    os.remove("channel.json"); os.remove("channel.json.sig")


def main(argv: list) -> int:
    if not argv or argv[0] in ("-h", "--help"): print(__doc__); return 0
    if not os.path.exists(PRIV) and argv[0] != "show":
        raise SystemExit(f"No signing key at {PRIV}. Run: tools/release.sh --new-key")
    doc, cmd = current(), argv[0]
    if cmd == "show":
        print(json.dumps(doc, indent=2)); return 0
    if cmd in ("hold", "unhold"):
        if len(argv) != 2: raise SystemExit(f"tools/channel.py {cmd} <version>")
        held = set(doc.get("hold") or [])
        held.add(argv[1]) if cmd == "hold" else held.discard(argv[1])
        doc["hold"] = sorted(held)
    elif cmd == "out":
        if len(argv) != 3: raise SystemExit("tools/channel.py out <version> <share, 0 to 1>")
        share = float(argv[2])
        if not 0 <= share <= 1: raise SystemExit("A share is between 0 and 1.")
        doc.setdefault("rollout", {})[argv[1]] = share
        if share >= 1: doc["rollout"].pop(argv[1])       # all the way out is the same as saying nothing
    else:
        raise SystemExit(f"No such thing as `{cmd}`. Try: show, hold, unhold, out")
    sign_and_publish(write(doc))
    print(json.dumps({k: doc[k] for k in ("hold", "rollout") if doc.get(k)}, indent=2))
    print("\nPublished. Hubs pick this up within half an hour, and always before they install.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
