#!/usr/bin/env bash
# Puts a backup back. home-hub-restore.path starts this when brain-data/restore.request appears next to
# restore.tar.gz (the brain parks the panel's upload there). Stops the house, unpacks data/ over brain-data
# and driver/ over driver-layer (keeping this hub's own address in .env), starts everything again.
set -uo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
DL="$DIR/driver-layer"; DATA="$DL/brain-data"
REQ="$DATA/restore.request"; TAR="$DATA/restore.tar.gz"; STATE="$DATA/restore.json"; LOG="$DATA/restore.log"
{ [ -f "$REQ" ] && [ -f "$TAR" ]; } || exit 0
rm -f "$REQ"
STARTED="$(date +%s)"
printf '{"state":"running","started":%s}\n' "$STARTED" > "$STATE"
fail() { printf '{"state":"failed","started":%s,"finished":%s,"log":"restore.log"}\n' "$STARTED" "$(date +%s)" > "$STATE"; exit 1; }
{
  cd "$DL" || exit 1
  tar -tzf "$TAR" | grep -qx 'manifest.json' || { echo "not a backup"; exit 1; }
  TMP="$(mktemp -d)"
  tar -xzf "$TAR" -C "$TMP" || exit 1
  docker compose stop
  [ -d "$TMP/data" ] && cp -a "$TMP/data/." "$DATA/"
  if [ -d "$TMP/driver" ]; then
    KEEP_IP="$(grep '^HUB_IP=' .env 2>/dev/null || true)"; KEEP_HOST="$(grep '^HUB_HOST=' .env 2>/dev/null || true)"
    cp -a "$TMP/driver/." "$DL/"
    [ -n "$KEEP_IP" ] && sed -i "s|^HUB_IP=.*|$KEEP_IP|" .env
    [ -n "$KEEP_HOST" ] && sed -i "s|^HUB_HOST=.*|$KEEP_HOST|" .env
  fi
  rm -rf "$TMP" "$TAR"
  docker compose up -d
} > "$LOG" 2>&1 || fail
printf '{"state":"done","started":%s,"finished":%s}\n' "$STARTED" "$(date +%s)" > "$STATE"
