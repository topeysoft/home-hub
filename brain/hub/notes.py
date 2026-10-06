# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What changed, in words a household reads.

One file per release in `releases/`, written by hand, checked by `tools/release-manifest.py` and
copied into the brain's image. That last part is the whole design: the notes a hub shows are the
notes for the code it is actually running, because they were built into the same image. Nothing is
fetched, so there is nothing to verify separately and nothing to go wrong with the internet down,
and the history is free -- the image carries every release file up to its own version.

The panel reads these on the wall the morning after the hub updated itself (docs/updates.md, piece 3
made that the ordinary case, which is what makes the morning after the right place for them) and
under *This hub → What's new* afterwards.
"""
from __future__ import annotations      # so tools/release-manifest.py can import this on an older python3

import os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES = Path(os.environ.get("HUB_NOTES") or ROOT.parent / "releases")
FILE = re.compile(r"^(\d+\.\d+(?:\.\d+)?)\.md$")     # 0.3.0.md; README.md and anything else is not a release


def order(version: str) -> tuple:
    """Newest first, by version and not by name: 0.10.0 comes after 0.9.0."""
    return tuple(int(p) for p in re.findall(r"\d+", version or "0"))


def parse(text: str) -> dict:
    """The two sections, and nothing clever. `what` is the bullets; `details` is the rest verbatim."""
    what, details, where = [], [], None
    for line in (text or "").splitlines():
        head = line.strip().lower().lstrip("#").strip()
        if line.startswith("#"):
            where = "what" if "what" in head else "details" if "detail" in head else None
            continue
        if where == "what" and line.strip().startswith(("-", "*")):
            what.append(line.strip()[1:].strip())
        elif where == "details":
            details.append(line)
    return {"what": what, "details": "\n".join(details).strip()}


def read(version: str) -> dict | None:
    """The notes for one version, or None. `v0.3.0` and `0.3.0` are the same release."""
    v = (version or "").lstrip("vV")
    if not v: return None
    try: text = (NOTES / f"{v}.md").read_text()
    except OSError: return None
    return {"version": v} | parse(text)


def history(limit: int = 20) -> list:
    """Every release this build carries notes for, newest first. Its own is the first of them."""
    try: files = [f for f in NOTES.iterdir() if FILE.match(f.name)]
    except OSError: return []
    out = []
    for f in sorted(files, key=lambda f: order(FILE.match(f.name).group(1)), reverse=True)[:limit]:
        v = FILE.match(f.name).group(1)
        try: out.append({"version": v} | parse(f.read_text()))
        except OSError: pass
    return out
