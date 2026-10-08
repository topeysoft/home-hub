#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The screen on a unit that has one: keep the startup splash up until the product answers, let the
# splash finish, then hand the screen to the panel. elyir-wall.service runs it twice:
#
#   wall.sh wait   as root, before the browser: waits for the product, tells the splash, lets it end
#   wall.sh run    as the wall's own user: cage with Chromium on the panel, full screen
#
# When only the browser restarts, the splash is long gone and `wait` returns at once, so a screen
# coming back is a few seconds of nothing rather than the whole startup again.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=plymouth/elyir/timing.sh
. "$HERE/plymouth/elyir/timing.sh"
READY_URL=${ELYIR_READY_URL:-http://localhost/alive}
PANEL_URL=${ELYIR_PANEL_URL:-http://localhost/?screen=1}   # a screen, so it asks which room it is in (design/companion/, C)

# Seconds since the splash first drew, from when systemd says plymouth-start finished.
splash_seconds() {
  local since now
  since=$(systemctl show -p ActiveEnterTimestampMonotonic --value plymouth-start.service 2>/dev/null || echo 0)
  now=$(awk '{print $1}' /proc/uptime)
  awk -v s="${since:-0}" -v n="$now" 'BEGIN { if (s == 0) print 0; else print n - s / 1000000 }'
}

browser() {
  local b
  for b in chromium chromium-browser; do command -v "$b" >/dev/null 2>&1 && { echo "$b"; return; }; done
  echo chromium
}

case "${1:-}" in
  wait)
    until curl -fsS -m 2 -o /dev/null "$READY_URL"; do sleep 1; done
    if plymouth --ping 2>/dev/null; then
      plymouth update --status=elyir:ready || true
      # The ending starts once the house has had its moment, and takes ENDING seconds.
      sleep "$(awk -v a="$READY_AFTER" -v s="$(splash_seconds)" -v e="$ENDING" 'BEGIN { w = a - s; if (w < 0) w = 0; print w + e + 0.1 }')"
      plymouth quit --retain-splash || true
    fi ;;
  run)
    # A desktop browser ignores the panel's user-scalable=no, so a stray two-finger touch would zoom
    # the wall and a sideways swipe would go back a page; both are switched off here instead.
    exec cage -- "$(browser)" --kiosk --noerrdialogs --disable-infobars --no-first-run \
      --ozone-platform=wayland --disable-session-crashed-bubble --check-for-update-interval=31536000 \
      --disable-pinch --overscroll-history-navigation=0 \
      "$PANEL_URL" ;;
  *) echo "usage: $0 wait|run" >&2; exit 2 ;;
esac
