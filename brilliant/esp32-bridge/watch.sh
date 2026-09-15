#!/bin/sh
# Reset the bridge and stream what it hears. Run, wait ~40s for "[ble] bridge up",
# then go interact with the switch.
cd "$(dirname "$0")"
exec ../.venv/bin/python monitor.py /dev/cu.usbserial-0001 "${1:-180}"
