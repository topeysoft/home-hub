#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Keeps this unit's Wi-Fi awake. A Pi's radio dozing between beacons misses the frames sent to
# everyone at once -- a name being looked up, the router handing out a new key for exactly those
# frames -- and once it has missed the key it stays deaf to all of them until it rejoins. On 9 Oct
# 2026 a kitchen screen lost hub.local for three hours that way while every direct packet still
# arrived, so it looked fine and no tap reached the house. A box on mains has nothing to save.
#
# Two halves: NetworkManager is told for every connection from now on, and any wireless interface up
# now is woken without waiting for it to rejoin. Safe to run again; run as root by install.sh (through
# host/harden.sh) on a hub and by startup/install.sh on a screen.
set -uo pipefail
NM="${HUB_NM:-/etc/NetworkManager}"
NET="${HUB_NET:-/sys/class/net}"
have() { command -v "$1" >/dev/null 2>&1; }

if [ -d "$NM" ]; then
  conf="$NM/conf.d/home-hub-wifi.conf"
  want=$'[connection]\n# 2 is off: host/wifi-awake.sh\nwifi.powersave = 2'
  if [ "$(cat "$conf" 2>/dev/null)" != "$want" ]; then
    mkdir -p "$NM/conf.d" && printf '%s\n' "$want" > "$conf"
    have nmcli && nmcli general reload conf >/dev/null 2>&1
    echo "  wifi: power saving off from now on"
  fi
fi

iw=$(command -v iw || echo /usr/sbin/iw)
[ -x "$iw" ] || exit 0
for dev in "$NET"/*/wireless; do
  [ -e "$dev" ] || continue
  dev=$(basename "$(dirname "$dev")")
  "$iw" dev "$dev" get power_save 2>/dev/null | grep -q ': on' || continue
  "$iw" dev "$dev" set power_save off 2>/dev/null && echo "  wifi: $dev woken"
done
exit 0
