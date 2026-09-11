#!/usr/bin/env bash
# Applies an update the panel asked for. home-hub-update.path starts this the moment
# brain-data/update.request appears; install.sh does the actual work (code to whichever release or
# commit this hub's channel points at, images pulled, containers restarted) and update.json tells the
# brain, and so the panel, how it went. Safe to run by hand.
set -uo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
DATA="$DIR/driver-layer/brain-data"
REQ="$DATA/update.request"; STATE="$DATA/update.json"; LOG="$DATA/update.log"
[ -f "$REQ" ] || exit 0
# The hub's channel lives in the compose .env. Without passing it on, install.sh would fall back to
# its default and quietly move a hub that follows main onto releases.
CHANNEL="$(sed -n 's/^HUB_CHANNEL=//p' "$DIR/driver-layer/.env" 2>/dev/null | tail -1)"
CHANNEL="${CHANNEL:-release}"
rm -f "$REQ"
STARTED="$(date +%s)"
printf '{"state":"running","started":%s}\n' "$STARTED" > "$STATE"
if HOME_HUB_DIR="$DIR" HOME_HUB_CHANNEL="$CHANNEL" "$DIR/install.sh" > "$LOG" 2>&1; then
  printf '{"state":"done","started":%s,"finished":%s,"commit":"%s"}\n' "$STARTED" "$(date +%s)" "$(git -C "$DIR" rev-parse HEAD 2>/dev/null || echo unknown)" > "$STATE"
else
  printf '{"state":"failed","started":%s,"finished":%s,"log":"update.log"}\n' "$STARTED" "$(date +%s)" > "$STATE"
  exit 1
fi
