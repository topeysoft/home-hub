#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Is there already a hub on this Wi-Fi? Prints its address (http://hub.local) and exits 0, or prints
# nothing and exits 1. A unit with a screen asks this on its first start, before it installs a hub of
# its own: a house that has one gets a second screen, not a second house (design/companion/, C).
#
# A hub announces itself as _home-hub._tcp (install.sh), and is believed only if /phones/me answers
# the way a hub does -- the same proof the tablet's kiosk asks for. It is asked by its name, not its
# address: a hub's front door answers hub.local and the address it had when it was installed, and the
# router may have handed it another since. This unit's own announcements are skipped. FIND_FOR seconds
# (default 20) covers a network that is still coming up.
set -uo pipefail
FIND_FOR=${FIND_FOR:-20}

mine=" $(hostname -I 2>/dev/null) 127.0.0.1 "
until_at=$(( $(date +%s) + FIND_FOR ))
while :; do
  # =;iface;proto;name;type;domain;host;address;port;txt -- resolved answers only, IPv4 only
  while IFS=';' read -r kind _ proto _ _ _ host addr port _; do
    [ "$kind" = "=" ] && [ "$proto" = "IPv4" ] || continue
    case "$mine" in *" $addr "*) continue ;; esac
    at="$addr"; base="http://$addr"; [ -n "$host" ] && { at="$host"; base="http://$host"; }
    [ "$port" = 80 ] || base="$base:$port"
    if curl -fsS -m 3 --resolve "$at:$port:$addr" "$base/phones/me" 2>/dev/null | grep -q '"paired"'; then
      echo "$base"
      exit 0
    fi
  done < <(avahi-browse -rpt _home-hub._tcp 2>/dev/null)
  [ "$(date +%s)" -ge "$until_at" ] && exit 1
  sleep 2
done
