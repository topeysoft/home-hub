#!/usr/bin/env bash
# Radios come and go. Finds the Zigbee and Z-Wave sticks, records them in .env, and starts or stops
# their containers. install.sh runs this once; a udev rule runs it again whenever a USB serial device
# appears or disappears, so plugging a stick in is all anyone has to do.
#   radios.sh          detect, update .env, start and stop containers
#   radios.sh detect   detect and update .env only (install.sh, before the first start)
#
# Radios on the network instead of USB (an Ethernet Zigbee coordinator such as the SLZB-06, a PoE
# Z-Wave dongle): put ZIGBEE_NET=tcp://host:port and/or ZWAVE_NET=tcp://host:port in .env by hand.
# They count as found, and the host needs no USB at all, which is what makes a NUC, a VM and a Pi
# the same hub.
#
# The Nortek/GoControl HUSBZB-1 ("HubZ Smart Home Controller") is two radios on one plug: -if00 is its
# Z-Wave 500-series port, which works as is; -if01 is an old EM3581 Zigbee chip whose stock firmware
# Zigbee2MQTT cannot drive, so it is left alone and Zigbee waits for an MG24-class stick.
set -euo pipefail
cd "$(dirname "$0")"
[ "${1:-}" = "detect" ] || sleep "${RADIOS_SETTLE:-2}"    # udev's by-id links land a moment after the device
touch .env
ZB_NET="$(grep '^ZIGBEE_NET=' .env | cut -d= -f2- || true)"
ZW_NET="$(grep '^ZWAVE_NET=' .env | cut -d= -f2- || true)"

sticks() { find /dev/serial/by-id -maxdepth 1 -mindepth 1 -printf '%f\n' 2>/dev/null || true; }
ZB="$(sticks | grep -i -E 'skyconnect|zbt-|zbdongle|sonoff|mg24|cc2652|zigbee|efr32|nabu' | grep -v -i hubz | head -1 || true)"
ZW="$(sticks | grep -i -E 'zooz|z-wave|zwave|aeotec|800|pzg23|hubz.*if00' | head -1 || true)"

set_env() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
del_env() { sed -i "/^$1=/d" .env; }

seed_zwave() {
  # Z-Wave JS UI's settings, written once: the stick (or its tcp:// address), the websocket HA connects
  # to, and network keys that must never change afterwards (every paired device is bound to them).
  [ -f zwave-js-ui/settings.json ] && return
  mkdir -p zwave-js-ui
  key() { head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' | tr a-f A-F; }
  cat > zwave-js-ui/settings.json <<EOF
{
  "mqtt": {"disabled": true},
  "gateway": {"authEnabled": false},
  "zwave": {
    "port": "${ZW_NET:-/dev/zwave}",
    "serverEnabled": true, "serverPort": 3000, "serverHost": "0.0.0.0",
    "enableStatistics": false, "disclaimerVersion": 1, "logEnabled": false,
    "securityKeys": {"S0_Legacy": "$(key)", "S2_Unauthenticated": "$(key)", "S2_Authenticated": "$(key)", "S2_AccessControl": "$(key)"},
    "securityKeysLongRange": {"S2_Authenticated": "$(key)", "S2_AccessControl": "$(key)"}
  }
}
EOF
}

PROFILES=""
if [ -n "$ZB_NET" ]; then set_env ZIGBEE_SERIAL /dev/null; set_env ZIGBEE_PORT "$ZB_NET"; PROFILES="zigbee"
elif [ -n "$ZB" ]; then set_env ZIGBEE_SERIAL "/dev/serial/by-id/$ZB"; del_env ZIGBEE_PORT; PROFILES="zigbee"
else del_env ZIGBEE_SERIAL; del_env ZIGBEE_PORT; fi
if [ -n "$ZW_NET" ]; then set_env ZWAVE_SERIAL /dev/null; PROFILES="${PROFILES:+$PROFILES,}zwave"; seed_zwave
elif [ -n "$ZW" ]; then set_env ZWAVE_SERIAL "/dev/serial/by-id/$ZW"; PROFILES="${PROFILES:+$PROFILES,}zwave"; seed_zwave
else del_env ZWAVE_SERIAL; fi
set_env COMPOSE_PROFILES "${PROFILES:-none}"
echo "  Zigbee: ${ZB_NET:-${ZB:-none found}}"
echo "  Z-Wave: ${ZW_NET:-${ZW:-none found}}"
[ "${1:-}" = "detect" ] && exit 0

[ -n "$ZB$ZB_NET" ] || docker stop zigbee2mqtt >/dev/null 2>&1 || true
[ -n "$ZW$ZW_NET" ] || docker stop zwave-js-ui >/dev/null 2>&1 || true
docker compose up -d >/dev/null 2>&1
