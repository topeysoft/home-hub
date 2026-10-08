#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Gives a unit with its own screen Elyir's startup: a quiet boot, the splash from startup/, and the
# panel full screen once the product answers. Run once, as root, from first boot when a screen is
# connected (driver-layer/host/firstboot.sh), or by hand; running it again brings the splash up to
# date with this checkout.
set -euo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
HERE="$DIR/startup"
THEME=/usr/share/plymouth/themes/elyir
log() { printf '[startup] %s\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

log "packages: the splash, a one-window compositor, its display scaling and a browser"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends plymouth cage wlr-randr curl >/dev/null
apt-get install -y --no-install-recommends chromium >/dev/null 2>&1 \
  || apt-get install -y --no-install-recommends chromium-browser >/dev/null

log "the splash"
rm -rf "$THEME"; mkdir -p "$THEME"
cp "$HERE"/plymouth/elyir/*.png "$HERE"/plymouth/elyir/elyir.plymouth "$HERE"/plymouth/elyir/elyir.script "$THEME"/

# A Pi's boot says nothing of its own: no rainbow, no raspberries, no log, no cursor. Each edit
# checks first, so running this again changes nothing.
CFG=/boot/firmware/config.txt CMD=/boot/firmware/cmdline.txt
if [ -f "$CFG" ] && ! grep -q '^disable_splash=1' "$CFG"; then
  printf '\n# Elyir: the startup is ours from the first frame\ndisable_splash=1\n' >> "$CFG"
fi
if [ -f "$CMD" ]; then
  line=$(head -n1 "$CMD")
  line=${line//console=tty1/console=tty3}
  for arg in quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0 loglevel=3; do
    case " $line " in *" $arg "*) ;; *) line="$line $arg" ;; esac
  done
  printf '%s\n' "$line" > "$CMD"
fi
plymouth-set-default-theme -R elyir >/dev/null

log "the screen's own user and service"
id elyir-wall >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin elyir-wall
usermod -aG video,render,input elyir-wall
cat > /etc/pam.d/elyir-wall <<'PAM'
auth     required pam_unix.so nullok
account  required pam_unix.so
session  required pam_unix.so
session  required pam_systemd.so
PAM
install -m 0644 "$HERE/elyir-wall.service" /etc/systemd/system/elyir-wall.service
systemctl daemon-reload
systemctl enable elyir-wall.service >/dev/null
log "done; it shows from the next boot"
