#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The light strip's shipped image, as one file: what a strip is first flashed with, and what the hub
# offers a strip that is behind (brain/hub/bridge_updates.py, StripKind).
#
#   tools/build-strip.sh            build strip/firmware and merge it into releases/strip/
#   tools/build-strip.sh --dirty    build anyway from an unclean tree, and say so in the stamp
#
# The same shape as tools/build-bridge.sh, and the same reason to refuse an unclean tree: the stamp
# names a commit, and a stamp the image does not match is worse than none. ESP-IDF rather than
# PlatformIO, so it wants the environment strip/firmware/README.md describes; this sets it up the way
# that README does rather than trusting whatever shell it was run from.
set -euo pipefail
cd "$(dirname "$0")/.."
F=strip/firmware
OUT=releases/strip

STAMP="$(git rev-parse --short HEAD)"
DIRTY="$(git status --porcelain -- "$F/main" "$F/CMakeLists.txt" "$F/sdkconfig.defaults" "$F"/sdkconfig.defaults.* "$F"/*.csv)"
if [ -n "$DIRTY" ]; then
  if [ "${1:-}" != "--dirty" ]; then
    echo "The firmware sources are not clean, so a release built now would claim $STAMP and not be it:"
    echo "$DIRTY" | sed 's/^/    /'
    echo
    echo "Commit them, stash them, or build anyway with:  tools/build-strip.sh --dirty"
    exit 2
  fi
  STAMP="$STAMP+dirty"
  echo "building from an unclean tree; stamping $STAMP"
fi

export IDF_PYTHON_ENV_PATH="${IDF_PYTHON_ENV_PATH:-$HOME/.espressif/python_env/idf6.0_py3.10_env}"
# Not under -u: esp-matter's export.sh reads ESP_MATTER_PATH before it sets it.
set +u
# shellcheck disable=SC1091
. "${IDF_PATH:-$HOME/esp/esp-idf-v6.0.2}/export.sh" >/dev/null 2>&1
# shellcheck disable=SC1091
. "$HOME/esp/esp-matter/export.sh" >/dev/null 2>&1
set -u

# A release is never a test build and never a board's pin. sdkconfig is not in git, so a checkout that
# built before a default changed still carries the old answer; the two settings a release cannot ship
# without are checked by name rather than trusted.
cd "$F"
for want in CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y; do
  grep -qx "$want" sdkconfig 2>/dev/null || {
    echo "sdkconfig lacks $want -- it predates sdkconfig.defaults. Remove sdkconfig and run idf.py set-target esp32s3."; exit 1; }
done
grep -q '^CONFIG_ENABLE_OTA_REQUESTOR=y' sdkconfig && {
  echo "sdkconfig still turns Matter's own updates on. Remove sdkconfig and run idf.py set-target esp32s3."; exit 1; }
idf.py -DSTRIP_FW= -DDATA_PIN= -DSELFTEST= build >/dev/null
cd - >/dev/null

FW=$(sed -n 's/^#define STRIP_FW "\(.*\)"/\1/p' "$F/main/fwupdate.h")
grep -aq "$FW  chip" "$F/build/strip.bin" || { echo "the image does not say it is $FW"; exit 1; }
mkdir -p "$OUT"
# flash_args is ESP-IDF's own list of what goes where (bootloader 0x0, table 0x8000, otadata 0xf000,
# app 0x20000) with the flash settings in front, so the offsets are never restated here.
(cd "$F/build" && python -m esptool --chip esp32s3 merge-bin -o "../../../$OUT/esp32s3-ship.bin" @flash_args >/dev/null)
cat > "$OUT/esp32s3-ship.json" <<JSON
{"env": "strip", "chip": "esp32s3", "fw": "$FW", "offset": 0, "flash_mode": "dio", "flash_freq": "80m", "flash_size": "8MB",
 "sha256": "$(shasum -a 256 "$OUT/esp32s3-ship.bin" | cut -d' ' -f1)", "built": "$(date -u +%Y-%m-%dT%H:%M:%SZ)", "commit": "$STAMP"}
JSON
ls -la "$OUT/esp32s3-ship.bin"; cat "$OUT/esp32s3-ship.json"
