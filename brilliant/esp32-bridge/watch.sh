#!/bin/sh
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# Reset the bridge and stream what it hears. Run, wait ~40s for "[ble] bridge up",
# then go interact with the switch.
cd "$(dirname "$0")"
exec ../.venv/bin/python monitor.py /dev/cu.usbserial-0001 "${1:-180}"
