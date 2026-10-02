#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Brings the way in from outside up or down: the relay's client (frpc) and the away door on the house's
# own name (caddy/away/on.caddy). docs/away.md, step 4; design/address/ is what the household saw.
#
# home-hub-away.path starts this the moment brain-data/away.request appears. The brain writes two files
# and nothing else: away.request naming a WANT, and away.env carrying the values the house was handed
# when it claimed its name (hub/address.py). It never runs docker and holds no socket that could.
#
# THE REQUEST NAMES A WANT AND NEVER A COMMAND -- on, off, or forget -- checked here against a list
# written here. And every value in away.env is checked again, by its own pattern, before a single line
# of .env is written: these values arrive from a service on the internet by way of the brain, and .env
# is read by docker compose as root. Anything that does not match is dropped and said so in the log.
# restart.sh and update.sh make the same point; keep the three shaped alike.
#
#   on       the house's values into .env, `away` into the profiles, caddy and frpc up
#   off      HUB_AWAY=off, `away` out of the profiles, frpc gone, caddy back to the plain door
#   forget   off, and the house's name and secret taken out of .env as well
#
# Safe to run by hand.
set -uo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
DL="$DIR/driver-layer"; DATA="$DL/brain-data"
REQ="$DATA/away.request"; VALUES="$DATA/away.env"; DONE="$DATA/away.json"; LOG="$DATA/away.log"
ENV="$DL/.env"

[ -f "$REQ" ] || exit 0
WANT="$(sed -n 's/.*"want": *"\([a-z]*\)".*/\1/p' "$REQ" | head -1)"
rm -f "$REQ"

value() { grep -m1 "^$1=" "$VALUES" 2>/dev/null | cut -d= -f2-; }
set_env() { if grep -q "^$1=" "$ENV"; then sed -i "s|^$1=.*|$1=$2|" "$ENV"; else echo "$1=$2" >> "$ENV"; fi; }
del_env() { sed -i "/^$1=/d" "$ENV"; }

# COMPOSE_PROFILES is one line everybody shares (radios.sh owns zigbee and zwave); only `away` is ours.
profiles() {
  local kept; kept="$(grep '^COMPOSE_PROFILES=' "$ENV" | cut -d= -f2- | tr ',' '\n' | grep -vx -e away -e none -e '' | paste -sd, - || true)"
  if [ "$1" = add ]; then set_env COMPOSE_PROFILES "${kept:+$kept,}away"; else set_env COMPOSE_PROFILES "${kept:-none}"; fi
}

said() { printf '{"on": %s, "house": "%s", "at": %s, "said": "%s"}\n' "$1" "$2" "$(date +%s)" "$3" > "$DONE"; }

{
  echo "--- $(date -Is) away: ${WANT:-<nothing>}"
  touch "$ENV"
  case "$WANT" in
    on)
      HOUSE="$(value HUB_AWAY_HOUSE)"; SECRET="$(value HUB_RELAY_SECRET)"; TOKEN="$(value HUB_RELAY_TOKEN)"
      ADDR="$(value HUB_RELAY_ADDR)"; ZONE="$(value HUB_AWAY_ZONE)"
      looks() { echo "$2" | grep -Eqx "$1"; }
      NAME='[a-z0-9]([a-z0-9-]{0,28}[a-z0-9])?'; KEY='[A-Za-z0-9_-]{16,128}'; HOSTNAME='[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?'
      if ! { looks "$NAME" "$HOUSE" && looks "$KEY" "$SECRET" && looks "$KEY" "$TOKEN" && looks "$HOSTNAME" "$ADDR" && looks "$HOSTNAME" "$ZONE"; }; then
        echo "the values in away.env do not look like a house's -- nothing done"
        said false "" "The values for outside did not look right, so nothing was changed."
        exit 1
      fi
      set_env HUB_AWAY on
      set_env HUB_AWAY_HOUSE "$HOUSE"; set_env HUB_RELAY_SECRET "$SECRET"; set_env HUB_RELAY_TOKEN "$TOKEN"
      set_env HUB_RELAY_ADDR "$ADDR"; set_env HUB_AWAY_ZONE "$ZONE"
      profiles add
      cd "$DL" && docker compose up -d caddy frpc
      said true "$HOUSE" "Outside is on."
      ;;
    off|forget)
      set_env HUB_AWAY off
      if [ "$WANT" = forget ]; then
        for k in HUB_AWAY_HOUSE HUB_RELAY_SECRET HUB_RELAY_TOKEN HUB_RELAY_ADDR HUB_AWAY_ZONE; do del_env "$k"; done
      fi
      profiles remove
      cd "$DL" && { docker compose --profile away rm -sf frpc; docker compose up -d caddy; }
      said false "" "Outside is off."
      ;;
    *)
      echo "not something this hub knows how to do outside: ${WANT:-<nothing>} -- nothing done"
      exit 1
      ;;
  esac
} >> "$LOG" 2>&1
