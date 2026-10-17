#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Keeps the house's hub reachable from this screen when its name stops answering. A screen opens the
# hub by name (http://hub.local), and that name is found by asking everyone on the Wi-Fi at once: a
# screen whose Wi-Fi has stopped hearing those questions' answers can no longer find the hub, though
# the hub is right there. So each time the name does answer, the address goes into /etc/hosts, which
# the browser reads first; when it does not, the address last seen is the one kept. The hub moving to
# a new address is caught the next minute the name answers again.
#
# elyir-keep-hub.timer runs this as root every minute. A screen that opens an address, or this
# unit's own panel, has nothing to keep.
set -uo pipefail
HOSTS="${HUB_HOSTS:-/etc/hosts}"
MARK="# elyir: the house's hub, kept by startup/keep-hub.sh"
URL="${ELYIR_PANEL_URL:-http://localhost/}"

at=${URL#*://}; at=${at%%/*}; at=${at%%\?*}
host=${at%%:*}; port=80; [ "$at" = "$host" ] || port=${at#*:}
case "$host" in *.local) ;; *) exit 0 ;; esac

addr=$(avahi-resolve -4 -n "$host" 2>/dev/null | awk 'NR == 1 { print $2 }')
[ -n "$addr" ] || exit 0
curl -fsS -m 3 -o /dev/null --resolve "$host:$port:$addr" "http://$host:$port/alive" 2>/dev/null || exit 0

line=$(printf '%s\t%s\t%s' "$addr" "$host" "$MARK")
grep -qxF "$line" "$HOSTS" 2>/dev/null && exit 0
tmp=$(mktemp "$HOSTS.XXXXXX") || exit 1
{ grep -vF "$MARK" "$HOSTS" 2>/dev/null; printf '%s\n' "$line"; } > "$tmp"
chmod 644 "$tmp" && mv -f "$tmp" "$HOSTS"
echo "the hub is at $addr"
