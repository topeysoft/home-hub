#!/usr/bin/env bash
# One-line install on a fresh Raspberry Pi OS / Debian box:
#   curl -fsSL https://raw.githubusercontent.com/<you>/home-hub/main/install.sh | sudo bash
# or, from a checkout:  sudo ./install.sh
#
# Installs Docker, names the machine "hub" so it answers at http://hub.local, finds any Zigbee or
# Z-Wave stick, and starts everything. Safe to run again: it only fills in what is missing.
set -euo pipefail

REPO="${HOME_HUB_REPO:-https://github.com/temi/home-hub.git}"
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
HOSTNAME_WANTED="${HOME_HUB_HOSTNAME:-hub}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "Run me with sudo."; exit 1; }

say "1/5  Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || apt-get install -y docker-compose-plugin
systemctl enable --now docker >/dev/null 2>&1 || true

say "2/5  The code"
if [ -f "$(dirname "$0")/driver-layer/docker-compose.yml" ] && [ "$(cd "$(dirname "$0")" && pwd)" != "$DIR" ]; then
  mkdir -p "$DIR"; cp -R "$(cd "$(dirname "$0")" && pwd)/." "$DIR/"
elif [ ! -d "$DIR/.git" ]; then
  apt-get install -y git >/dev/null; git clone --depth 1 "$REPO" "$DIR"
else
  git -C "$DIR" pull --ff-only || true
fi
cd "$DIR/driver-layer"

say "3/5  A name on the network: $HOSTNAME_WANTED.local"
if [ "$(hostname)" != "$HOSTNAME_WANTED" ]; then
  hostnamectl set-hostname "$HOSTNAME_WANTED" 2>/dev/null || echo "$HOSTNAME_WANTED" > /etc/hostname
  sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME_WANTED/" /etc/hosts 2>/dev/null || true
fi
apt-get install -y avahi-daemon >/dev/null 2>&1 || true   # mDNS, so hub.local resolves on phones and tablets
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
docker compose pull -q 2>/dev/null || true
docker compose build -q brain
docker compose up -d --remove-orphans

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "Done. On a phone or tablet on the same Wi‑Fi open:"
echo "    http://$HOSTNAME_WANTED.local      (or http://$IP)"
echo "The screen walks you through the rest. The first start takes a minute or two."
