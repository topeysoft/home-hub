#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Publishing the Houses app to https://houses.elyir.app (relay/README.md, *The Houses app*).
#
#   tools/publish-houses.sh                        build HEAD from a clean checkout and publish it
#   REF=<commit> tools/publish-houses.sh           publish another commit
#   ROLLBACK=<version> tools/publish-houses.sh     switch back to a version still on the box
#   RELAY=root@relay.example tools/publish-houses.sh   another relay box
#
# Every phone that opens the app trusts this code with the passes to its houses, so it is only ever
# published from a commit, built in a clean checkout rather than this working tree, and unpacked into a
# new versioned directory on the relay's volume; `current` then switches to it in one rename. Nothing on
# the box is edited by hand, and the last few versions stay so a bad one can be switched back. The same
# shape as the printer app's publish, which lives in that app's own repository.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RELAY="${RELAY:-root@relay.elyir.app}"
SITE=https://houses.elyir.app/
DIR=/var/lib/relay/houses
KEEP=5
SSH=(ssh -o BatchMode=yes "$RELAY")
# What a version is called: the commit's date and its short hash. Checked before it is put in a remote
# command, since a rollback's name is typed by a person.
NAMED='^20[0-9]{2}\.[0-9]{2}\.[0-9]{2}-[0-9a-f]{7,40}$'

if [ -n "${ROLLBACK:-}" ]; then
  [[ "$ROLLBACK" =~ $NAMED ]] || { echo "not a version: $ROLLBACK (they look like 2026.10.03-1a2b3c4)" >&2; exit 1; }
  "${SSH[@]}" "cd $DIR && test -d '$ROLLBACK' && ln -sfn '$ROLLBACK' current.tmp && mv -T current.tmp current && readlink current"
  exit 0
fi

REF="${REF:-HEAD}"
VERSION="$(git -C "$ROOT" log -1 --format=%cd --date=format:%Y.%m.%d "$REF")-$(git -C "$ROOT" rev-parse --short "$REF")"
[[ "$VERSION" =~ $NAMED ]] || { echo "could not name a version for $REF" >&2; exit 1; }
WT="$(mktemp -d)"
trap 'git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true; rm -rf "$WT"' EXIT
git -C "$ROOT" worktree add -q --detach "$WT" "$REF"

# The dependencies are borrowed rather than installed when they are already here: from this checkout,
# or from the main one when this is a worktree of it. Otherwise installed clean from the lockfile.
MAIN="$(cd "$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)/.." && pwd)"
if [ -d "$ROOT/app/node_modules" ]; then
  ln -s "$ROOT/app/node_modules" "$WT/app/node_modules"
elif [ -d "$MAIN/app/node_modules" ]; then
  ln -s "$MAIN/app/node_modules" "$WT/app/node_modules"
else
  (cd "$WT/app" && npm ci --silent)
fi

echo "== build $VERSION"
(cd "$WT/app" && npm run build:houses --silent >/dev/null)
OUT="$WT/app/dist-houses"
[ -f "$OUT/index.html" ] || { echo "no $OUT/index.html: is build:houses set up at $REF?" >&2; exit 1; }
# The site's CSP allows no inline script, so a <script> tag with no src would be a blank page on every
# phone. Caught here rather than there.
if grep -oiE '<script[^>]*>' "$OUT/index.html" | grep -viqE '\ssrc='; then
  echo "index.html has an inline <script>; the relay's CSP would block it" >&2; exit 1
fi

echo "== publish to $RELAY:$DIR/$VERSION"
COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -czf - -C "$OUT" . |
  "${SSH[@]}" "set -e; mkdir -p $DIR/.incoming; rm -rf $DIR/.incoming/$VERSION; mkdir $DIR/.incoming/$VERSION
    tar -xzf - -C $DIR/.incoming/$VERSION
    chmod -R a+rX $DIR/.incoming/$VERSION
    rm -rf $DIR/$VERSION; mv $DIR/.incoming/$VERSION $DIR/$VERSION
    cd $DIR && ln -sfn $VERSION current.tmp && mv -T current.tmp current
    ls -1dt 20*/ 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -rf
    readlink current"

echo "== check"
curl -fsS -o /dev/null -w "$SITE -> %{http_code}\n" "$SITE"
