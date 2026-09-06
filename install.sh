#!/usr/bin/env bash
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

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
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
if [ -f "$(dirname "$0")/driver-layer/docker-compose.yml" ] && [ "$(cd "$(dirname "$0")" && pwd)" != "$DIR" ]; then
  mkdir -p "$DIR"; cp -R "$(cd "$(dirname "$0")" && pwd)/." "$DIR/"
elif [ ! -d "$DIR/.git" ]; then
  command -v git >/dev/null 2>&1 || pkg git; git clone --depth 1 "$REPO" "$DIR"
else
  git -C "$DIR" pull --ff-only || true
fi
cd "$DIR/driver-layer"

say "3/5  A name on the network: $HOSTNAME_WANTED.local"
if [ "$(hostname)" != "$HOSTNAME_WANTED" ]; then
  hostnamectl set-hostname "$HOSTNAME_WANTED" 2>/dev/null || echo "$HOSTNAME_WANTED" > /etc/hostname
  sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME_WANTED/" /etc/hosts 2>/dev/null || true
fi
pkg "$AVAHI" 2>/dev/null || true   # mDNS, so hub.local resolves on phones and tablets
systemctl enable --now avahi-daemon >/dev/null 2>&1 || true

say "4/5  Settings"
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
# radios: only start what is plugged in, now and whenever a stick is plugged in or pulled later
chmod +x radios.sh
./radios.sh detect
cat > /etc/udev/rules.d/90-home-hub-radios.rules <<RULES
# home-hub: a USB serial device came or went; start or stop the matching radio container
ACTION=="add", SUBSYSTEM=="tty", SUBSYSTEMS=="usb", RUN+="/usr/bin/systemd-run --no-block --collect $DIR/driver-layer/radios.sh"
ACTION=="remove", SUBSYSTEM=="tty", KERNEL=="ttyUSB*|ttyACM*", RUN+="/usr/bin/systemd-run --no-block --collect $DIR/driver-layer/radios.sh"
RULES
udevadm control --reload 2>/dev/null || true

say "5/5  Starting the house"
docker compose pull -q --ignore-buildable 2>/dev/null || true
if ! docker compose pull -q brain 2>/dev/null; then
  echo "  no published brain image for this machine (or no internet); building it here, which takes a few minutes"
  docker compose build -q brain
fi
docker compose up -d --remove-orphans

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "Done. On a phone or tablet on the same Wi‑Fi open:"
echo "    http://$HOSTNAME_WANTED.local      (or http://$IP)"
echo "The screen walks you through the rest. The first start takes a minute or two."
