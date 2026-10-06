#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Restarts the house at the rung the panel asked for. Two of them, and only two:
#
#   everything   the whole stack, engine included -- docker compose, recreated
#   machine      the box itself
#
# home-hub-restart.path starts this the moment brain-data/restart.request appears. The brain writes
# that file and nothing else: it never runs docker and holds no socket that could, which is the rule
# that stops anything able to write into the data volume from choosing what runs here.
#
# THE REQUEST NAMES A RUNG AND NEVER A COMMAND, and the word is checked again below against a list
# written here rather than sent from there. Anything else -- a unit name, a container, a path, a
# clever string -- is dropped on the floor and said so in the log. update.sh makes the same point
# about the version it is handed; keep the two shaped alike so a reader of one recognizes the other.
#
# The brain writes restart.json on its way down and reads it on the way back up, which is how the
# panel learns what this hub's own restart actually costs. Nothing here touches that file.
#
# Safe to run by hand.
set -uo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
DL="$DIR/driver-layer"; DATA="$DL/brain-data"
REQ="$DATA/restart.request"; LOG="$DATA/restart.log"
ALIVE="${HOME_HUB_ALIVE:-http://127.0.0.1:8300/alive}"
WAIT="${HOME_HUB_RESTART_WAIT:-240}"     # how long the brain has to come back before this puts it up again

[ -f "$REQ" ] || exit 0
RUNG="$(sed -n 's/.*"rung": *"\([a-z]*\)".*/\1/p' "$REQ" | head -1)"
rm -f "$REQ"

alive() { curl -fsS --max-time 5 "$ALIVE" >/dev/null 2>&1; }

came_back() {
  local deadline; deadline=$(( $(date +%s) + WAIT ))
  while [ "$(date +%s)" -lt "$deadline" ]; do alive && return 0; sleep 5; done
  return 1
}

{
  echo "--- $(date -Is) restart: $RUNG"
  case "$RUNG" in
    everything)
      cd "$DL" || exit 1
      docker compose up -d --force-recreate --remove-orphans
      # A stack that came up wrong is the case a household cannot fix from the wall, because the wall
      # is exactly what is missing. One more go before anybody has to be told to find the plug.
      if came_back; then echo "the house answered"; else
        echo "the brain did not answer in ${WAIT}s; bringing everything up again"
        docker compose up -d --force-recreate --remove-orphans
      fi
      ;;
    machine)
      # Compose starts on boot (`restart: unless-stopped`), so nothing else has to be arranged here.
      echo "rebooting"
      sync
      systemctl reboot
      ;;
    *)
      echo "not a rung this hub knows: ${RUNG:-<nothing>} -- nothing done"
      exit 1
      ;;
  esac
} >> "$LOG" 2>&1
