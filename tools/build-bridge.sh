#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The bridge puck's shipped image, as one file the hub can flash at 0x0.
#
#   tools/build-bridge.sh            build esp32s3-ship and merge it into releases/bridge/
#   tools/build-bridge.sh --dirty    build anyway from an unclean tree, and say so in the stamp
#
# The image has no secrets in it (brilliant/esp32-bridge/platformio.ini, [env:esp32s3-ship]): a puck
# flashed with it boots blank and is told everything over the cable by the brain (hub/bridge.py). It
# is committed to releases/bridge/ because the brain's image is built by CI from the repository and
# CI has no PlatformIO; this script is the one place the four parts and their offsets are known.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV=esp32s3-ship
B=brilliant/esp32-bridge
OUT=releases/bridge

# What ends up in the image, and therefore what the `commit` field below is a claim about.
#
# This builds the working tree but stamps HEAD, and platformio.ini has no src_filter, so everything
# under src/ is compiled -- including a file somebody else is halfway through writing. In a checkout
# two people share that is not hypothetical: a release was cut here while four untracked files sat in
# src/, and it only stayed honest because the build happened to run a minute before they landed. A
# stamp that names a commit the image does not match is worse than no stamp, because docs/updates.md
# is built on a signed manifest saying exactly what a release contains.
#
# Ignored files are not consulted, which is deliberate: include/secrets*.h lives there and the ship
# env is pointed at a header that does not exist precisely so it cannot see them.
shopt -s nullglob
COMPILED=("$B/src" "$B/include" "$B/platformio.ini" "$B"/*.csv)
shopt -u nullglob
STAMP="$(git rev-parse --short HEAD)"
DIRTY="$(git status --porcelain -- "${COMPILED[@]}")"
if [ -n "$DIRTY" ]; then
  if [ "${1:-}" != "--dirty" ]; then
    echo "The firmware sources are not clean, so a release built now would claim $STAMP and not be it:"
    echo "$DIRTY" | sed 's/^/    /'
    echo
    echo "Commit them, stash them, or build anyway with:  tools/build-bridge.sh --dirty"
    exit 2
  fi
  STAMP="$STAMP+dirty"
  echo "building from an unclean tree; stamping $STAMP"
fi

(cd "$B" && pio run -e "$ENV" >/dev/null)
ESPTOOL="$(ls -d "$HOME"/.platformio/packages/tool-esptoolpy/esptool.py 2>/dev/null || true)"
[ -n "$ESPTOOL" ] || { echo "no esptool.py under ~/.platformio/packages/tool-esptoolpy"; exit 1; }
FW=$(grep -o 'BRIDGE_FW "[^"]*"' "$B/src/config.h" | cut -d'"' -f2)
python3 "$ESPTOOL" --chip esp32s3 merge_bin -o "$OUT/$ENV.bin" --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0000 "$B/.pio/build/$ENV/bootloader.bin" \
  0x8000 "$B/.pio/build/$ENV/partitions.bin" \
  0xe000 "$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin" \
  0x10000 "$B/.pio/build/$ENV/firmware.bin" >/dev/null
cat > "$OUT/$ENV.json" <<JSON
{"env": "$ENV", "chip": "esp32s3", "fw": "$FW", "offset": 0, "flash_mode": "dio", "flash_freq": "80m", "flash_size": "16MB",
 "sha256": "$(shasum -a 256 "$OUT/$ENV.bin" | cut -d' ' -f1)", "built": "$(date -u +%Y-%m-%dT%H:%M:%SZ)", "commit": "$STAMP"}
JSON
ls -la "$OUT/$ENV.bin"; cat "$OUT/$ENV.json"
