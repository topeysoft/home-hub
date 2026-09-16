#!/usr/bin/env python3
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

COMPOSE = "driver-layer/docker-compose.yml"
BRAIN = "ghcr.io/topeysoft/home-hub-brain"
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
    verified release installs. The brain is left out -- it is named by the release, not by the file.

    Reading the default out of the shell expansion is the fiddly part, and getting it wrong is silent:
    an empty result would sign a manifest that pins nothing at all and looks perfectly well formed.
    Hence the count check below.
    """
    out, service = {}, None
    for line in open(COMPOSE):
        if m := re.match(r"^  ([a-z0-9-]+):\s*$", line): service = m.group(1)
        elif (m := re.match(r"^    image: (\S+)\s*$", line)) and service and service != "brain":
            ref = m.group(1)
            if m2 := re.fullmatch(r"\$\{[A-Z0-9_]+:-(.+)\}", ref): ref = m2.group(1)
            if not ref.startswith("$"): out[service] = ref
    return out


def main() -> int:
    if len(sys.argv) != 2: return print(__doc__, file=sys.stderr) or 2
    tag = sys.argv[1]
    commit = git("rev-list", "-n", "1", tag)
    version = tag.lstrip("vV")
    notes_file = f"releases/{version}.md"                        # piece 4 writes these; empty until then
    try: notes = open(notes_file).read().strip()
    except OSError: notes = ""
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
