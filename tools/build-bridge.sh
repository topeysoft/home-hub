#!/usr/bin/env bash
# The bridge puck's shipped image, as one file the hub can flash at 0x0.
#
#   tools/build-bridge.sh            build esp32s3-ship and merge it into releases/bridge/
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
 "sha256": "$(shasum -a 256 "$OUT/$ENV.bin" | cut -d' ' -f1)", "built": "$(date -u +%Y-%m-%dT%H:%M:%SZ)", "commit": "$(git rev-parse --short HEAD)"}
JSON
ls -la "$OUT/$ENV.bin"; cat "$OUT/$ENV.json"
