#!/usr/bin/env python3
"""Reset the board and stream its serial output (no TTY required)."""
import sys, time, serial
port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-0001"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60
s = serial.Serial(port, 115200, timeout=0.3)
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
