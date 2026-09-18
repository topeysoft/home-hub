#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stream the bridge's serial output (no TTY required).

    monitor.py [port] [seconds] [--no-reset]

Resets the board first unless --no-reset is given. With --no-reset the port is
opened with DTR/RTS deasserted up front, because on macOS simply opening the
port with pyserial's defaults pulses DTR and reboots an ESP32 anyway.
"""
import sys, time, serial
args = [a for a in sys.argv[1:] if not a.startswith("--")]
port = args[0] if len(args) > 0 else "/dev/cu.usbserial-0001"
secs = float(args[1]) if len(args) > 1 else 60
s = serial.Serial()
s.port, s.baudrate, s.timeout = port, 115200, 0.3
s.dtr = False
s.rts = False
s.open()
if "--no-reset" not in sys.argv:
    s.setDTR(False); s.setRTS(True); time.sleep(0.15); s.setRTS(False)  # pulse EN
end = time.time() + secs
buf = b""
while time.time() < end:
    d = s.read(4096)
    if d:
        buf += d
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            print(line.decode("utf-8", "replace").rstrip())
            sys.stdout.flush()
s.close()
