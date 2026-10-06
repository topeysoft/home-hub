#!/bin/sh
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The certificate for the house's name at home -- 192-168-86-53.<house>.home.elyir.app -- kept current.
#
# Runs inside the stock lego image (docker-compose.yml, lan-cert), so there is no ACME code of ours. The
# challenge is DNS-01, because a LAN address is the one place a CA's validator can never reach; lego's
# `httpreq` provider hands the TXT record to the registration service with the house's own name and
# secret (relay/service/home.py), and the service's DNS server answers it. No house holds a DNS
# credential, and the certificate covers this one name -- there is no wildcard anywhere under the zone.
#
# Caddy reads the result as bundle.pem through a loopback-only file server (caddy/away/on.caddy), and
# until there is one it simply has no certificate for this name: nothing else on the front door waits
# for it. A renewal lands without restarting anything. docs/away.md, *The alias that covers home*.
set -u
NAME="${HUB_LAN_NAME:-}"
API="${HUB_RELAY_API:-https://api.elyir.app}"
DIR=/lan
case "$NAME" in
  *.home.*) ;;
  *) echo "no name at home yet (HUB_LAN_NAME is '$NAME'); waiting"; sleep 3600; exit 0 ;;
esac
export HTTPREQ_ENDPOINT="$API/acme" HTTPREQ_USERNAME="${HUB_AWAY_HOUSE:-}" HTTPREQ_PASSWORD="${HUB_RELAY_SECRET:-}"
SERVER="${LEGO_SERVER:-https://acme-v02.api.letsencrypt.org/directory}"
# Only for a test in miniature, where no real delegation exists for lego's propagation check to follow.
FLAGS="${LEGO_FLAGS:-}"
CERT="$DIR/certificates/$NAME.crt"; KEY="$DIR/certificates/$NAME.key"
# lego will not run without an account email. Let's Encrypt has sent no email since 2025, so this is a
# label and nothing is ever delivered to it; it names nothing the certificate itself does not.
EMAIL="${HUB_AWAY_HOUSE:-house}@${NAME#*.home.}"

while true; do
  if [ -f "$CERT" ]; then
    # shellcheck disable=SC2086  # FLAGS is a list of flags, split on purpose
    /lego --accept-tos --email "$EMAIL" --server "$SERVER" --dns httpreq $FLAGS --domains "$NAME" --path "$DIR" renew --days 30 --no-random-sleep
  else
    # shellcheck disable=SC2086
    /lego --accept-tos --email "$EMAIL" --server "$SERVER" --dns httpreq $FLAGS --domains "$NAME" --path "$DIR" run
  fi
  if [ -f "$CERT" ] && [ -f "$KEY" ]; then
    umask 077
    cat "$CERT" "$KEY" > "$DIR/bundle.tmp" && mv "$DIR/bundle.tmp" "$DIR/bundle.pem"
    sleep 43200         # twice a day is plenty: lego renews 30 days before the end
  else
    sleep 900           # the relay or the house was not ready; try again in a quarter of an hour
  fi
done
