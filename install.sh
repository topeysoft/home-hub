#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# One-line install on any fresh Linux box: a Raspberry Pi 5, an Intel NUC, a VM, anything running
# Debian, Ubuntu, Raspberry Pi OS or Fedora with systemd:
#   curl -fsSL https://raw.githubusercontent.com/topeysoft/home-hub/main/install.sh | sudo bash
# or, from a checkout:  sudo ./install.sh
#
# Installs Docker, names the machine "hub" so it answers at http://hub.local, finds any Zigbee or
# Z-Wave stick now and whenever one is plugged in later, pulls the brain image (built for amd64 and
# arm64 by CI; built here only if the pull fails), and starts everything. Safe to run again: it only
# fills in what is missing. Nothing in here is specific to a Pi; that lives in host/firstboot.sh.
set -euo pipefail

REPO="${HOME_HUB_REPO:-https://github.com/topeysoft/home-hub.git}"
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
HOSTNAME_WANTED="${HOME_HUB_HOSTNAME:-hub}"
# Which code this hub follows. "release" is the newest version tag: nothing reaches a house until
# somebody tags it. "main" and "development" follow those branches commit by commit, which is what a
# hub being worked on wants — HOME_HUB_CHANNEL=development sudo ./install.sh. The brain is told, so
# the panel offers the same one. Anything else is a typo, and a typo lands on releases.
CHANNEL="${HOME_HUB_CHANNEL:-release}"
case "$CHANNEL" in main|development) BRANCH="$CHANNEL" ;; *) CHANNEL="release"; BRANCH="main" ;; esac

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
# Where this has got to, for the panel to draw. Only when update.sh asks for it: somebody running
# this by hand is reading the output and needs no file. It writes A PHASE FROM A FIXED LIST and never
# a sentence — brain/hub/updates.py owns the words, which is what stops anything that can write into
# the data volume from putting a sentence on somebody's wall. Second argument is extra JSON.
phase() { [ -n "${HUB_PROGRESS:-}" ] || return 0
  printf '{"phase":"%s","at":%s%s}\n' "$1" "$(date +%s)" "${2:-}" >> "$HUB_PROGRESS" 2>/dev/null || true; }
[ "$(id -u)" -eq 0 ] || { echo "Run me with sudo."; exit 1; }
if command -v apt-get >/dev/null 2>&1; then
  pkg() { DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" >/dev/null; }; AVAHI=avahi-daemon
elif command -v dnf >/dev/null 2>&1; then
  pkg() { dnf install -y "$@" >/dev/null; }; AVAHI=avahi
else
  echo "This needs apt or dnf (Debian, Ubuntu, Raspberry Pi OS, Fedora)."; exit 1
fi
command -v systemctl >/dev/null 2>&1 || { echo "This needs systemd."; exit 1; }

say "1/5  Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || pkg docker-compose-plugin
systemctl enable --now docker >/dev/null 2>&1 || true

say "2/5  The code"
phase fetching
# $DIR is a deployment, not a place anyone edits: it ends up exactly where the channel points.
HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION=""
# The newest version tag, by version order rather than by date, so a fix tagged on an older line
# does not look newer than the release it came after.
want_ref() {
  [ "$CHANNEL" != "release" ] && { echo "origin/$BRANCH"; return; }
  git -C "$DIR" tag -l 'v*' --sort=-v:refname | head -1
}
# Whether a release is what the maker says it is, and what it says to run. host/verify.sh comes from
# the checkout as it is *now* -- the one the last verified update left behind -- and is read before
# anything moves, so the code doing the checking is never the code being installed.
# shellcheck source=driver-layer/host/verify.sh
[ -f "$DIR/driver-layer/host/verify.sh" ] && . "$DIR/driver-layer/host/verify.sh"
go_to_ref() {
  local ref target; ref="$(want_ref)"
  if [ -z "$ref" ]; then
    ref="origin/main"; echo "  nothing tagged yet, so: main"
  fi
  target="$ref"
  # A hub following a branch is a hub being worked on: there are no manifests for commits, and an
  # override that skipped the check for releases would only end up pasted into a house.
  if [ "$CHANNEL" = "release" ] && command -v verify_release >/dev/null 2>&1; then
    verify_release "$ref" "$DIR"; case $? in
      0) target="$VERIFIED_COMMIT" ;;
      2) echo "  this hub has no release key yet, so $ref is taken on trust this once" ;;
      *) echo "  staying on $(git -C "$DIR" describe --tags --always 2>/dev/null): nothing is installed that cannot be checked"
         echo "$ref" > "$DIR/driver-layer/brain-data/update.refused" 2>/dev/null || true
         return 1 ;;
    esac
  fi
  git -C "$DIR" reset -q --hard "$target" && git -C "$DIR" clean -qfd -e driver-layer/
  case "$ref" in v*) VERSION="${ref#v}" ;; esac
  echo "  $CHANNEL: ${ref} — $(git -C "$DIR" log -1 --format='%h %s' | cut -c1-60)"
}
if [ -d "$DIR/.git" ]; then
  command -v git >/dev/null 2>&1 || pkg git
  if git -C "$DIR" fetch -q --tags --force origin "$BRANCH" 2>/dev/null; then
    # 3, not 1: a release that could not be checked is a different thing from an install that broke,
    # and a household tapping Try again cannot fix it. host/update.sh tells the two apart.
    go_to_ref || exit 3
  else
    echo "  could not reach $REPO; keeping the code that is here"
  fi
elif [ -f "$HERE/driver-layer/docker-compose.yml" ] && [ "$HERE" != "$DIR" ]; then
  mkdir -p "$DIR"; cp -R "$HERE/." "$DIR/"     # a first install from a copied checkout, without internet
else
  # A full clone rather than --depth 1: the tags are how a release is found, and they are only
  # a few megabytes here.
  command -v git >/dev/null 2>&1 || pkg git
  git clone -q "$REPO" "$DIR" && { go_to_ref || exit 3; }
fi
cd "$DIR/driver-layer"
# Code and container move together: a hub on v0.2.0 runs the 0.2.0 image, not whatever is newest. A
# verified release has already said which image, by digest; this is the fallback for a hub following
# a branch, whose image is tagged with the branch's name, and for the first install of a release that
# predates the signing.
if [ -z "${HUB_BRAIN_IMAGE:-}" ]; then
  if [ -n "$VERSION" ]; then export HUB_BRAIN_IMAGE="ghcr.io/topeysoft/home-hub-brain:${VERSION}"
  elif [ "$CHANNEL" != "release" ]; then export HUB_BRAIN_IMAGE="ghcr.io/topeysoft/home-hub-brain:${BRANCH}"
  fi
fi
# The Matter bridge is ours too, and it and the brain have a contract between them -- what the bridge
# is handed for each device, and how long a request to open the door lasts. A hub running a new brain
# against a bridge it had cached from a month ago is a version skew nobody would enjoy finding, so it
# is named by the release exactly the way the brain is rather than left on :latest. docs/matter.md.
if [ -z "${HUB_BRIDGE_IMAGE:-}" ]; then
  if [ -n "$VERSION" ]; then export HUB_BRIDGE_IMAGE="ghcr.io/topeysoft/home-hub-matter-bridge:${VERSION}"
  elif [ "$CHANNEL" != "release" ]; then export HUB_BRIDGE_IMAGE="ghcr.io/topeysoft/home-hub-matter-bridge:${BRANCH}"
  fi
fi
export HUB_CHANNEL="$CHANNEL"

say "3/5  A name on the network: $HOSTNAME_WANTED.local"
if [ "$(hostname)" != "$HOSTNAME_WANTED" ]; then
  hostnamectl set-hostname "$HOSTNAME_WANTED" 2>/dev/null || echo "$HOSTNAME_WANTED" > /etc/hostname
  sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME_WANTED/" /etc/hosts 2>/dev/null || true
fi
pkg "$AVAHI" 2>/dev/null || true   # mDNS, so hub.local resolves on phones and tablets
# ...and a service record, for the things that cannot resolve a .local name at all. Plenty of wall
# tablets cannot; the kiosk in kiosk/ asks for this and gets an address that always works.
mkdir -p /etc/avahi/services 2>/dev/null && cat > /etc/avahi/services/home-hub.service <<'MDNS' 2>/dev/null || true
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">%h</name>
  <service>
    <type>_home-hub._tcp</type>
    <port>80</port>
    <txt-record>path=/</txt-record>
  </service>
</service-group>
MDNS
systemctl enable --now avahi-daemon >/dev/null 2>&1 || true
systemctl reload-or-restart avahi-daemon >/dev/null 2>&1 || true

say "4/5  Settings"
# The host as an appliance: watchdog, a cap on container logs, a cap on the journal. Exit 10 means
# the log cap is new and every container is made again below, once, to take it.
chmod +x host/harden.sh
RECREATE=""
if host/harden.sh; then :; else
  case $? in 10) RECREATE="--force-recreate" ;; *) echo "  (host hardening did not finish; the house starts anyway)" ;; esac
fi
# The key this hub checks releases against, copied out of the checkout once and never again: $DIR is
# the thing being updated, so a key kept only there could be replaced by the same push it exists to
# catch. The first install trusts the repository it came from; every update after it trusts this file.
# host/verify.sh reads it. A flashed image narrows that first-install trust, because the image was
# built from a tag and carries the key already.
KEYDIR="${HOME_HUB_KEYS:-/etc/home-hub/release-keys.d}"
if [ ! -d "$KEYDIR" ] && ls host/release-keys.d/*.pub >/dev/null 2>&1; then
  mkdir -p "$KEYDIR" && cp host/release-keys.d/*.pub "$KEYDIR"/ && chmod 0644 "$KEYDIR"/*.pub
  echo "  $(ls "$KEYDIR"/*.pub | wc -l | tr -d ' ') release key(s) installed; from here on this hub installs nothing it cannot check"
fi
if [ ! -f .env ]; then
  TZ_NOW="$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || echo UTC)"
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  {
    echo "TZ=$TZ_NOW"
    echo "HUB_HOST=$HOSTNAME_WANTED.local"
    echo "HUB_IP=${IP:-127.0.0.1}"
    echo "ZWAVE_SESSION_SECRET=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' )"
  } > .env
fi
# The key the brain and the Matter bridge share, so the bridge gets past the phone gate without being
# a phone. docs/matter.md. Added if it is missing rather than written with the block above, because a
# hub installed before sharing existed needs one too -- and never rewritten, because rotating it would
# cut a running bridge off mid-command for no reason anybody asked for.
grep -q '^HUB_SHARE_TOKEN=' .env || echo "HUB_SHARE_TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' )" >> .env
# Rewritten every run: the channel is a property of this hub, and re-running with a different one
# is how it is changed.
sed -i '/^HUB_CHANNEL=/d' .env 2>/dev/null || true
echo "HUB_CHANNEL=$CHANNEL" >> .env
# Whether this hub can check what it installs. The brain reads it to decide whether it may update in
# the night on its own: a hub that cannot verify a release waits to be asked, because updating by
# itself from something nothing checks is the supply-chain problem with the person taken out of it.
sed -i '/^HUB_VERIFIED=/d' .env 2>/dev/null || true
if ls "$KEYDIR"/*.pub >/dev/null 2>&1; then echo "HUB_VERIFIED=1" >> .env; fi
# The image pin belongs here too, not only in this script's own environment. A compose brought up by
# any other hand -- somebody debugging, or host/update.sh putting an old image back after a rollback
# -- would otherwise resolve :latest and break the rule that code and container move together.
sed -i '/^HUB_BRAIN_IMAGE=/d' .env 2>/dev/null || true
if [ -n "${HUB_BRAIN_IMAGE:-}" ]; then echo "HUB_BRAIN_IMAGE=$HUB_BRAIN_IMAGE" >> .env; fi
sed -i '/^HUB_BRIDGE_IMAGE=/d' .env 2>/dev/null || true
if [ -n "${HUB_BRIDGE_IMAGE:-}" ]; then echo "HUB_BRIDGE_IMAGE=$HUB_BRIDGE_IMAGE" >> .env; fi
# ...and the rented images the verified release pinned by digest. Written fresh every run and left
# out entirely when there is nothing to pin, so the tags in docker-compose.yml are what a hub falls
# back to rather than a digest from some release it is no longer on.
sed -i '/^HUB_IMG_/d' .env 2>/dev/null || true
for v in ${HUB_IMAGE_VARS:-}; do echo "$v=${!v}" >> .env; done
# Messages take a password: made once, written into .env, handed to every part by compose.
chmod +x mqtt-auth.sh
./mqtt-auth.sh
# radios: only start what is plugged in, now and whenever a stick is plugged in or pulled later
chmod +x radios.sh
./radios.sh detect
cat > /etc/udev/rules.d/90-home-hub-radios.rules <<RULES
# home-hub: a USB serial device came or went; start or stop the matching radio container
ACTION=="add", SUBSYSTEM=="tty", SUBSYSTEMS=="usb", RUN+="/usr/bin/systemd-run --no-block --collect $DIR/driver-layer/radios.sh"
ACTION=="remove", SUBSYSTEM=="tty", KERNEL=="ttyUSB*|ttyACM*", RUN+="/usr/bin/systemd-run --no-block --collect $DIR/driver-layer/radios.sh"
RULES
udevadm control --reload 2>/dev/null || true
# updates, restores and restarts: the panel writes brain-data/<thing>.request; these units see it and act.
# The watchdog is the one with no request behind it: it runs on its own clock and catches a house that
# stopped answering when nobody is there to notice (docs/restart.md, piece 5).
chmod +x host/update.sh host/restore.sh host/channel.sh host/restart.sh host/watchdog.sh host/network.sh
for u in home-hub-update.service home-hub-update.path home-hub-restore.service home-hub-restore.path \
         home-hub-restart.service home-hub-restart.path home-hub-watchdog.service home-hub-watchdog.timer \
         home-hub-channel.service home-hub-channel.timer \
         home-hub-network.service home-hub-network.path home-hub-network.timer; do
  sed "s#/opt/home-hub#$DIR#g" "host/$u" > "/etc/systemd/system/$u"
done
systemctl daemon-reload 2>/dev/null || true
systemctl enable --now home-hub-update.path home-hub-restore.path home-hub-restart.path \
                       home-hub-watchdog.timer home-hub-channel.timer \
                       home-hub-network.path home-hub-network.timer >/dev/null 2>&1 || true
# ...and write the first picture of this hub's network now, so the panel's Network row is a fact
# from the first minute rather than blank until the timer's first tick (docs/network.md, piece 2).
HOME_HUB_DIR="$DIR" ./host/network.sh >/dev/null 2>&1 || true
# ...and ask once now, so a hub coming up after a hold was published knows about it before its first night.
HOME_HUB_DIR="$DIR" ./host/channel.sh >/dev/null 2>&1 || true

say "5/5  Starting the house"
phase downloading
# Pre-pull everything the compose file pins. A tag that no longer exists on the registry would
# otherwise surface as a wall of daemon errors from `up`, with none of the other images fetched and
# nothing started, so say which reference is missing in one line instead.
if ! PULLED="$(docker compose pull -q --ignore-buildable 2>&1)"; then
  echo "$PULLED" | sed -n 's/.*failed to resolve reference "\([^"]*\)".*/  could not fetch \1 — that pin is not on the registry/p' | sort -u
fi
if PULL="$(docker compose pull -q brain 2>&1)"; then
  echo "  brain image: $(docker image inspect "${HUB_BRAIN_IMAGE:-ghcr.io/topeysoft/home-hub-brain:latest}" --format '{{index .RepoDigests 0}}' 2>/dev/null | cut -d@ -f2 | cut -c1-19)"
else
  case "$PULL" in
    *denied*|*unauthorized*|*401*|*403*) echo "  the published brain image is not public (GitHub package visibility); building it here from the code above, which takes a few minutes" ;;
    *) echo "  could not pull the brain image (no internet?); building it here from the code above, which takes a few minutes" ;;
  esac
  # Stamp what is being built. CI passes these when it publishes the image; a build here passed
  # nothing, so the brain came up calling itself "dev" with no commit -- and updates.py reads an
  # empty commit as "nobody can tell", which quietly switches update checking off on exactly the
  # hubs that had to build their own. The checkout this was built from is the answer, and it is
  # right there.
  BUILT_COMMIT="$(git -C "$DIR" rev-parse HEAD 2>/dev/null || echo "")"
  BUILT_VERSION="${VERSION:-main-$(git -C "$DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)}"
  # A digest names an image that exists on a registry, and nothing can build one: docker refuses
  # outright with "refusing to create a tag with a digest reference". So a verified release, which
  # pins by digest on purpose, could not fall back to building at all -- the install would fail on
  # every hub that cannot reach the registry, which is the one case the fallback exists for. Build
  # under a name of this hub's own instead.
  #
  # What that costs is worth being honest about. The code is still the commit the signed record
  # named, so this is built from exactly the source the release described; what is lost is the
  # pinned binary, and with it the pinned base images the Dockerfile does not name by digest. It is
  # a weaker guarantee than pulling what CI built, and a much stronger one than not updating.
  case "${HUB_BRAIN_IMAGE:-}" in
    *@sha256:*)
      export HUB_BRAIN_IMAGE="home-hub/brain:$BUILT_VERSION"
      sed -i '/^HUB_BRAIN_IMAGE=/d' .env 2>/dev/null || true
      echo "HUB_BRAIN_IMAGE=$HUB_BRAIN_IMAGE" >> .env
      echo "  built here, so it is $HUB_BRAIN_IMAGE rather than the digest the release named" ;;
  esac
  phase building
  docker compose build -q --build-arg "HUB_VERSION=$BUILT_VERSION" --build-arg "HUB_COMMIT=$BUILT_COMMIT" brain
fi
# Which containers this is actually about to recreate. It is the difference between "a few minutes"
# for every update and the one sentence docs/updates.md has been promising since its first draft: the
# brain alone is a blink, the engine moving is a minute where the wall switches still work and the
# app does not. A service moves when the image it is about to run is not the image its container is
# running now, which catches a release that pinned a new digest and a tag that moved under an
# unchanged name alike. Anything this cannot work out is simply not said.
moving() {
  docker compose config --format json 2>/dev/null | python3 -c '
import json, subprocess, sys
def ask(*a):
    try: return subprocess.run(a, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception: return ""
try: cfg = json.load(sys.stdin)
except Exception: sys.exit(0)
out = []
for name, svc in sorted((cfg.get("services") or {}).items()):
    want = svc.get("image") or ""
    if not want: continue
    c = svc.get("container_name") or name
    ref = ask("docker", "inspect", "--format", "{{.Config.Image}}", c)
    if not ref: continue                       # not running: it starts, and nobody notices a start
    if ref != want: out.append(name); continue
    a, b = ask("docker", "inspect", "--format", "{{.Image}}", c), ask("docker", "image", "inspect", "--format", "{{.Id}}", want)
    if a and b and a != b: out.append(name)
print(json.dumps(out))
' 2>/dev/null
}
MOVING=""
# An `if`, not a `&&`: this script runs under `set -e`, and a plain test that comes out false on
# every ordinary first install would take the installer down with it.
if [ -n "${HUB_PROGRESS:-}" ]; then MOVING="$(moving || true)"; fi
case "$MOVING" in \[*\]) phase restarting ",\"moving\":$MOVING" ;; *) phase restarting ;; esac
# shellcheck disable=SC2086
docker compose up -d --remove-orphans $RECREATE

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "Done. On a phone or tablet on the same Wi‑Fi open:"
echo "    http://$HOSTNAME_WANTED.local      (or http://$IP)"
echo "The screen walks you through the rest. The first start takes a minute or two."
