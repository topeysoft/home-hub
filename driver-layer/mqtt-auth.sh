#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Messages (Mosquitto) take a password. This makes one the first time and writes the broker's
# password file from it, so every part that talks to the broker -- Zigbee2MQTT, Ring, the engine --
# gets the same credential from .env and nothing on the Wi-Fi gets in without it.
#   MQTT_USER / MQTT_PASSWORD in .env    made once, kept; docker-compose.yml hands them to each part
#   mosquitto/config/passwd              rewritten from .env on every run, by the broker's own tool
#   ring-mqtt/config.json                rendered from config.template.json with the password in its
#                                        mqtt_url: in Docker, ring-mqtt reads only that file
# install.sh runs this on every install and update. On a Mac, run it once from driver-layer/ before
# docker-compose.mac.yml comes up, then the brain from its venv reads the same .env.
set -euo pipefail
cd "$(dirname "$0")"
touch .env
[ ! -s .env ] || [ -z "$(tail -c1 .env)" ] || echo >> .env    # a last line with no newline would swallow what is appended next
get() { grep "^$1=" .env | tail -1 | cut -d= -f2- || true; }
if [ -z "$(get MQTT_USER)" ]; then echo "MQTT_USER=hub" >> .env; fi
if [ -z "$(get MQTT_PASSWORD)" ]; then
  # Letters and digits only: it travels in a URL (ring-mqtt's MQTTURL) and in YAML, so nothing needs quoting.
  echo "MQTT_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32)" >> .env
fi
chmod 600 .env 2>/dev/null || true     # it now holds a password; the brain gets it from compose, not from this file
USER_="$(get MQTT_USER)"; PASS_="$(get MQTT_PASSWORD)"
IMG="$(get HUB_IMG_MOSQUITTO)"; IMG="${IMG:-eclipse-mosquitto:2}"    # the same image that runs the broker, so the hash is one it reads
mkdir -p mosquitto/config
# The broker's own tool, with its own default hash, in the image that will read the file. Written
# fresh every run (the tool will not overwrite, so the old file goes first), so a password changed
# by hand in .env takes on the next install.
rm -f mosquitto/config/passwd
docker run --rm -v "$PWD/mosquitto/config:/mosquitto/config" --entrypoint mosquitto_passwd "$IMG" \
  -c -b /mosquitto/config/passwd "$USER_" "$PASS_" >/dev/null
# The broker wants this owner-only and will one day refuse anything wider. On the hub it is owned by
# the broker's own user (1883); on a Mac, where nobody can chown, it stays readable and the broker warns.
if chown 1883:1883 mosquitto/config/passwd 2>/dev/null; then chmod 600 mosquitto/config/passwd; else chmod 644 mosquitto/config/passwd; fi
docker kill -s HUP mosquitto >/dev/null 2>&1 || true    # a running broker re-reads the file; a stopped one is fine
# Ring's config, with the password in the one place ring-mqtt reads it from. The template is the
# tracked file; this one is not, because it holds the password. Keys a person changed are kept.
URL="mqtt://$USER_:$PASS_@mosquitto:1883"
if command -v python3 >/dev/null 2>&1; then
  python3 - "$URL" <<'PY'
import json, os, sys
t, p = "ring-mqtt/config.template.json", "ring-mqtt/config.json"
d = json.load(open(p)) if os.path.exists(p) else {}
for k, v in json.load(open(t)).items(): d.setdefault(k, v)
if d.get("mqtt_url") != sys.argv[1]:
    d["mqtt_url"] = sys.argv[1]
    with open(p, "w") as f: json.dump(d, f, indent=2); f.write("\n")
PY
else
  [ -f ring-mqtt/config.json ] || cp ring-mqtt/config.template.json ring-mqtt/config.json
  sed -i.bak -E "s|\"mqtt_url\": *\"[^\"]*\"|\"mqtt_url\": \"$URL\"|" ring-mqtt/config.json && rm -f ring-mqtt/config.json.bak
fi
chmod 600 ring-mqtt/config.json 2>/dev/null || true
echo "  Messages: password set for '$USER_'"
