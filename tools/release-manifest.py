#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the signed record of what a release actually is.

A hub's answer to "what may run as root in this house" used to be "whatever the newest v* tag points
at". Tags move. This writes down, for one tag, the commit and every image by digest, so that a hub
can be told what a release is by something an attacker who owns the GitHub account still cannot
forge -- the signature over this file. See docs/updates.md, piece 2.

    tools/release-manifest.py v0.3.0 > release.json

Digests are resolved by asking the registries, anonymously, rather than by asking the local Docker
daemon: a laptop that happens to have an old layer cached would otherwise sign a digest nobody else
can pull. Nothing here needs docker installed.

The shape is deliberately flat and one field to a line. The hub reads it with sed in a shell script,
and it only ever reads it *after* the signature has been checked, so the parser is looking at a file
this tool wrote rather than at anything a stranger chose.
"""
import base64, json, os, re, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "brain"))
from hub import notes as release_notes            # noqa: E402 -- the path above is what makes it importable

COMPOSE = "driver-layer/docker-compose.yml"
BRAIN = "ghcr.io/topeysoft/home-hub-brain"
# Ours too, and named by the release for the same reason the brain is: the two have a contract
# between them -- the shape of what the bridge is handed per device, and how long a request to open
# the door stays live -- so a hub must never be able to run a new one against an old one.
BRIDGE = "ghcr.io/topeysoft/home-hub-matter-bridge"
ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))


def git(*args: str) -> str:
    return subprocess.run(("git",) + args, capture_output=True, text=True, check=True).stdout.strip()


def split_ref(ref: str) -> tuple[str, str, str]:
    """`caddy:2` -> (registry-1.docker.io, library/caddy, 2). Docker's own shorthand, spelled out."""
    name, _, tag = ref.partition("@")[0].rpartition(":")
    if not name: name, tag = tag, "latest"
    host, _, rest = name.partition("/")
    if "." not in host and ":" not in host and host != "localhost":
        host, rest = "registry-1.docker.io", name if "/" in name else f"library/{name}"
    return host, rest, tag


def credential() -> str:
    """A GitHub token, for the releases whose package is not public. The maker running this has one."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN", "CR_PAT"):
        if os.environ.get(var): return os.environ[var]
    try: return subprocess.run(("gh", "auth", "token"), capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError): return ""


def digest(ref: str) -> str:
    """The digest a `docker pull` of this reference would land on, asked of the registry itself."""
    host, name, tag = split_ref(ref)
    realm = "https://auth.docker.io/token?service=registry.docker.io" if host == "registry-1.docker.io" \
        else f"https://{host}/token?service={host}"
    head = {}
    if host == "ghcr.io" and (cred := credential()):
        head["Authorization"] = "Basic " + base64.b64encode(f"x:{cred}".encode()).decode()
    try:
        req = urllib.request.Request(f"{realm}&scope=repository:{name}:pull", headers=head)
        with urllib.request.urlopen(req, timeout=30) as r:
            token = json.loads(r.read())["token"]
        req = urllib.request.Request(f"https://{host}/v2/{name}/manifests/{tag}",
                                     headers={"Accept": ACCEPT, "Authorization": f"Bearer {token}"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            d = r.headers.get("Docker-Content-Digest")
    except urllib.error.HTTPError as e:
        why = {401: "it is not public, and no GitHub token here could see it",
               403: "this token is not allowed to read it",
               404: "there is no such tag on the registry"}.get(e.code, f"the registry said {e.code}")
        raise SystemExit(f"Cannot resolve {ref}: {why}.\n"
                         f"  A release names every image by digest, so this has to be readable before it can be signed.\n"
                         f"  For a package of our own that is private: make it public, or run this with GITHUB_TOKEN set.")
    except urllib.error.URLError as e:
        raise SystemExit(f"Cannot reach the registry for {ref}: {e.reason}")
    if not d: raise SystemExit(f"{ref}: the registry gave no digest")
    return f"{ref.partition('@')[0].rpartition(':')[0]}@{d}"


def rented() -> dict:
    """Every image the compose file pins, by service.

    Each line reads `image: ${HUB_IMG_THING:-thing:1.2}`: the tag inside is the record of what was
    tested and the default a hub falls back to, and the digest that tag means *here* is what a
    verified release installs. The two of ours -- the brain and the Matter bridge -- are left out: they
    are named by the release, not by the file, and they have to move together.

    Reading the default out of the shell expansion is the fiddly part, and getting it wrong is silent:
    an empty result would sign a manifest that pins nothing at all and looks perfectly well formed.
    Hence the count check below.
    """
    ours = ("brain", "matter-bridge")     # named by the release, not rented from anybody
    out, service = {}, None
    for line in open(COMPOSE):
        if m := re.match(r"^  ([a-z0-9-]+):\s*$", line): service = m.group(1)
        elif (m := re.match(r"^    image: (\S+)\s*$", line)) and service and service not in ours:
            ref = m.group(1)
            if m2 := re.fullmatch(r"\$\{[A-Z0-9_]+:-(.+)\}", ref): ref = m2.group(1)
            if not ref.startswith("$"): out[service] = ref
    return out


# What a release note may not say. Deliberately short: a checker that tried to detect jargon in
# general would either miss it or block a real sentence, and the point is to catch the three ways
# these actually go wrong -- somebody pastes a commit subject, names a file, or writes for the repo.
# The first three come straight from the rule the panel already holds: nothing on it ever mentions
# Home Assistant, entities, or YAML.
BANNED = [
    (re.compile(r"home ?assistant", re.I), "the panel never names Home Assistant, and a release note is the panel"),
    (re.compile(r"\bentit(y|ies)\b", re.I), "a household has lights and speakers, not entities"),
    (re.compile(r"\b(yaml|docker|container|systemd|mqtt)\b", re.I), "a word from inside the hub, not from inside a house"),
    (re.compile(r"\b[\w-]+\.(py|ts|vue|yml|yaml|sh|json|md)\b"), "a filename"),
    (re.compile(r"^(feat|fix|chore|refactor|docs|test|perf)(\([^)]*\))?:", re.I), "a commit subject"),
    (re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b"), "a commit hash"),
]


def read_notes(version: str) -> dict:
    """The release's own notes, checked. A release without them does not ship.

    Refusing here rather than warning is the point: the alternative is a family reading
    `feat(sort): implement scrolling behavior for New devices list` off their kitchen wall, and
    that only ever happens because nobody was stopped.
    """
    path = Path("releases") / f"{version}.md"
    try: n = release_notes.parse(path.read_text())
    except OSError:
        raise SystemExit(f"No release notes at {path}.\n"
                         f"  Every release ships with them -- see releases/README.md for the shape and the rules.")
    if not n["what"]:
        raise SystemExit(f"{path} has no 'What's new' lines. See releases/README.md.")
    if len(n["what"]) > 6:
        raise SystemExit(f"{path} has {len(n['what'])} 'What's new' lines. Two to four; the rest is Details.")
    for line in n["what"]:
        if len(line) > 160: raise SystemExit(f"{path}: this line is too long for a wall:\n  {line}")
        for pattern, why in BANNED:
            if pattern.search(line):
                raise SystemExit(f"{path}: {why}:\n  {line}")
    return n


def main() -> int:
    if len(sys.argv) != 2: return print(__doc__, file=sys.stderr) or 2
    tag = sys.argv[1]
    commit = git("rev-list", "-n", "1", tag)
    version = tag.lstrip("vV")
    notes = read_notes(version)
    found = rented()
    # A manifest that pins nothing is the failure this cannot be allowed to have: it verifies, it
    # installs, and every image comes down by tag exactly as if none of this existed.
    if len(found) < 5: raise SystemExit(f"Only {len(found)} images found in {COMPOSE}; that is not right, and a "
                                        "manifest that pins nothing would still verify. Check the image lines.")
    images = {s: digest(r) for s, r in sorted(found.items())}
    print(json.dumps({
        "schema": 1,
        "version": tag,
        "commit": commit,
        "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "brain": digest(f"{BRAIN}:{version}"),
        "bridge": digest(f"{BRIDGE}:{version}"),
        "images": images,
        # The oldest release that may move straight to this one. An upgrade path nobody tested is
        # better refused than discovered in somebody's house.
        "min_from": "v0.1.0",
        "urgent": False,
        "notes": notes,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
