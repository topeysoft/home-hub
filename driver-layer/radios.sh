#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
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
#   radios.sh which <by-id name>   say what one name would be taken for, and change nothing
set -euo pipefail
cd "$(dirname "$0")"

# ---- what a stick is taken for -------------------------------------------------------------
#
# MATCHED AGAINST THE VENDOR AND PRODUCT ONLY, NEVER THE SERIAL NUMBER. A by-id name is
# usb-<vendor>_<product>_<serial>-if<NN>[-port<N>], and the serial is an arbitrary string the maker
# chose. Matching the whole line meant `800` -- which is there for an 800-series Z-Wave stick --
# claimed an ESP32 bridge puck whose serial happened to read 5A46080020. zwave-js-ui was handed it as
# /dev/zwave, held it open, and retried every fifteen seconds for as long as it was plugged in; the
# hub could then never talk to its own puck, and every attempt to set one up died with "multiple
# access on port". One substring in one pattern, and the house could not adopt a bridge.
#
# The trailing token is only taken for a serial when it looks like one (four or more alphanumerics),
# so a product that simply ends in a word keeps it.
product() { printf '%s' "$1" | sed -E 's/-if[0-9]+(-port[0-9]+)?$//; s/_[A-Za-z0-9]{4,}$//'; }

is_zigbee() {
  # The HubZ's Zigbee half is an EM3581 that Zigbee2MQTT cannot drive (see the note above), so it is
  # never the answer here even though it says Zigbee on the tin.
  case "$(product "$1")" in *[Hh][Uu][Bb][Zz]*) return 1 ;; esac
  product "$1" | grep -qiE 'skyconnect|zbt-|zbdongle|sonoff|mg24|cc2652|zigbee|efr32|nabu'
}

is_zwave() {
  # ...and its Z-Wave half is -if00, which is the one that works as is. The interface is the only
  # part of the name outside the product that is ever read, and only for this one device.
  case "$(product "$1")" in
    *[Hh][Uu][Bb][Zz]*) case "$1" in *-if00*) return 0 ;; *) return 1 ;; esac ;;
  esac
  product "$1" | grep -qiE 'zooz|z-?wave|aeotec|800|pzg23'
}

# Say what one name would be taken for and stop. For the tests, and for anybody on a hub asking the
# question this script got wrong: `./radios.sh which usb-1a86_USB_Single_Serial_5A46080020-if00`.
if [ "${1:-}" = "which" ]; then
  n="${2:-}"
  if [ -z "$n" ]; then echo "usage: radios.sh which <by-id name>" >&2; exit 2; fi
  if is_zigbee "$n"; then echo zigbee
  elif is_zwave "$n"; then echo zwave
  else echo none; fi
  exit 0
fi

[ "${1:-}" = "detect" ] || sleep "${RADIOS_SETTLE:-2}"    # udev's by-id links land a moment after the device
touch .env
ZB_NET="$(grep '^ZIGBEE_NET=' .env | cut -d= -f2- || true)"
ZW_NET="$(grep '^ZWAVE_NET=' .env | cut -d= -f2- || true)"
# Profiles this script does not own -- voice, and whatever comes after it -- are carried through.
# COMPOSE_PROFILES is one line everybody shares, and this script's job is the radios: a stick being
# unplugged must not switch off the hub's voice, which is what rewriting the whole line would do.
KEPT="$(grep '^COMPOSE_PROFILES=' .env | cut -d= -f2- | tr ',' '\n' | grep -vx -e zigbee -e zwave -e none | paste -sd, - || true)"

# What this script actually decides. If none of it moves, nothing wants restarting -- and
# restarting things that did not need it is not free: `docker compose up -d` re-creates the
# brain, and a brain that restarts forgets which USB devices were already there. Plugging in
# a bare ESP32 therefore bounced the brain, which then treated the new board as part of the
# scenery it woke up to and never offered it. A board that could not be added, because of a
# line in a shell script about radios.
radio_state() { grep -E '^(ZIGBEE_SERIAL|ZIGBEE_PORT|ZWAVE_SERIAL|COMPOSE_PROFILES)=' .env 2>/dev/null | sort || true; }
BEFORE="$(radio_state)"

sticks() { find /dev/serial/by-id -maxdepth 1 -mindepth 1 -printf '%f\n' 2>/dev/null || true; }
ZB=""; ZW=""
for s in $(sticks); do
  [ -n "$ZB" ] || ! is_zigbee "$s" || ZB="$s"
  [ -n "$ZW" ] || ! is_zwave "$s" || ZW="$s"
done

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
ALL="$PROFILES${PROFILES:+${KEPT:+,}}$KEPT"
set_env COMPOSE_PROFILES "${ALL:-none}"
echo "  Zigbee: ${ZB_NET:-${ZB:-none found}}"
echo "  Z-Wave: ${ZW_NET:-${ZW:-none found}}"
[ "${1:-}" = "detect" ] && exit 0

if [ "$BEFORE" = "$(radio_state)" ]; then
  echo "  no radio changed -- leaving the containers alone"
  exit 0
fi

[ -n "$ZB$ZB_NET" ] || docker stop zigbee2mqtt >/dev/null 2>&1 || true
[ -n "$ZW$ZW_NET" ] || docker stop zwave-js-ui >/dev/null 2>&1 || true
docker compose up -d >/dev/null 2>&1
