#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# What the maker is saying about releases right now, as against what a release is.
#
# A release manifest is signed once and never changes, which is exactly right for "what is v0.3.1"
# and exactly wrong for "do not install v0.3.1, we got it wrong". That second thing has to be
# sayable in the minutes after somebody notices, without cutting another tag, and it has to reach
# hubs that have not updated yet. So it is a separate small signed file, republished rather than
# re-released: tools/release.sh --hold puts it up in seconds.
#
# **The host fetches and checks it; the brain only reads the result.** The brain has no way to verify
# a signature -- no ed25519 anywhere in its dependencies -- so a channel file it fetched itself would
# be a stranger's word about whether this house should update. Here it is checked against the same
# keys as a release and written into the data volume as a local file that only root wrote.
#
# Three rules, and the reasoning matters more than the code:
#
#   * **It may only ever slow a hub down.** It withholds versions; it never names one to install, so
#     a forged one cannot point a house at an old release. The worst it can do is stop updates.
#   * **Missing, stale or unsigned means no hold at all.** Failing the other way would hand anybody
#     who can block a network the power to freeze every hub on the version it is on -- and the whole
#     point of updating overnight is that updates actually land. A hold is a maker's convenience, not
#     a security control; the signature over the release is the security control.
#   * **`made` is inside the signature**, so an old file cannot be replayed as a new one. After
#     STALE it is ignored, which bounds how long a replayed hold can withhold anything.
set -uo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
DATA="$DIR/driver-layer/brain-data"
OUT="$DATA/channel.json"
STALE="${HOME_HUB_CHANNEL_STALE:-2592000}"     # 30 days. A hold meant to outlive that gets re-signed.
# The keys, the signature check and the releases address all live there. Without it there is nothing
# to check a channel file against, and a hub that cannot check one must not be told by one.
if [ ! -f "$DIR/driver-layer/host/verify.sh" ]; then
  echo "channel: $DIR/driver-layer/host/verify.sh is missing, so nothing can be checked" >&2
  rm -f "$OUT"; exit 0
fi
# shellcheck source=driver-layer/host/verify.sh
. "$DIR/driver-layer/host/verify.sh"
CHANNEL_URL="${HOME_HUB_CHANNEL_URL:-$RELEASES/channel/channel.json}"

drop() { rm -f "$OUT"; exit "${1:-0}"; }       # no file is the answer "nothing is being held"

[ "$(held_keys)" -gt 0 ] || drop 0             # a hub that cannot check one is not told by one
command -v curl >/dev/null 2>&1 || drop 0
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

curl -fsSL "$CHANNEL_URL" -o "$tmp/channel.json" || drop 0
curl -fsSL "$CHANNEL_URL.sig" -o "$tmp/channel.json.sig" || drop 0
signed_by_us "$tmp/channel.json" "$tmp/channel.json.sig" || {
  echo "channel: not signed by any key this hub trusts; ignoring it" >&2; drop 0; }

made="$(sed -n 's/^ *"made": "\([^"]*\)".*/\1/p' "$tmp/channel.json" | head -1)"
# date(1) differs between GNU and BusyBox; python3 is on every host this installs on and is what the
# brain is written in anyway. Anything unparseable is treated as too old, which fails the safe way.
age="$(python3 - "$made" <<'PY' 2>/dev/null || echo 99999999
import calendar, sys, time
try: print(int(time.time() - calendar.timegm(time.strptime(sys.argv[1], "%Y-%m-%dT%H:%M:%SZ"))))
except Exception: print(99999999)
PY
)"
if [ "$age" -gt "$STALE" ]; then
  echo "channel: that file was made $((age / 86400)) days ago; ignoring it" >&2; drop 0
fi

mkdir -p "$DATA" && cp "$tmp/channel.json" "$OUT" && chmod 0644 "$OUT"
