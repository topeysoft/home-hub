#!/usr/bin/env python3
"""Talk to a bridge puck over its USB cable: the hub's side of esp32-bridge/src/config.h.

    puck_cable.py <port> hello                       who is this, and is it blank
    puck_cable.py <port> status                      wifi / mqtt / proxy / light, one line
    puck_cable.py <port> write [--from secrets.h] [--wifi SSID PASS] [--mqtt HOST PORT USER PASS]
                               [--keys NETKEY APPKEY IV] [--base mesh] [--label Brilliant] [--no-apply]
    puck_cable.py <port> wipe                        back to blank

`write` is what the hub does when a puck is on its cable (design/puck/Cable.dc.html): every value goes
over hex-encoded, so nothing needs quoting, then `apply` restarts the puck on the new config and this
waits for it to come back and say so. --from reads a desk header (include/secrets*.h) so a puck can be
given exactly what it was compiled with -- which is how this was first proven. Anything given on the
command line wins over the header.

The port is opened with DTR and RTS held low: on macOS pyserial's defaults pulse DTR and reset an
ESP32 on open, and a puck that reboots every time the hub says hello is not one you can talk to.
"""
import argparse
import re
import sys
import time

import serial


def hx(s: str) -> str:
    return s.encode("utf-8").hex()


def open_port(port: str, tries: int = 40) -> serial.Serial:
    """Open without resetting the board; after `apply` the USB port re-enumerates, so keep trying."""
    for i in range(tries):
        try:
            s = serial.Serial()
            s.port, s.baudrate, s.timeout = port, 115200, 0.4
            s.dtr = False
            s.rts = False
            s.open()
            return s
        except (serial.SerialException, OSError):
            if i == tries - 1:
                raise
            time.sleep(0.5)
    raise RuntimeError("unreachable")


class Puck:
    ANSWERS = ("bridge ", "status ", "ok ", "err ")

    def __init__(self, port: str):
        self.port = port
        self.s = open_port(port)
        self.s.reset_input_buffer()

    def ask(self, line: str, wait: float = 3.0) -> str:
        """Send one line, return the first line back that is an answer (the firmware's own log is noise)."""
        self.s.write((line + "\n").encode())
        self.s.flush()
        end = time.time() + wait
        buf = b""
        while time.time() < end:
            d = self.s.read(4096)
            if not d:
                continue
            buf += d
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                t = raw.decode("utf-8", "replace").strip()
                if t.startswith(self.ANSWERS):
                    return t
        raise TimeoutError(f"no answer to {line.split()[0]!r} from {self.port}")

    def hello(self, patience: float = 12.0) -> dict:
        """Opening the port resets the puck (the S3's USB-serial peripheral does that on its own, DTR or
        no DTR), so the first hello goes into the bootloader and is lost. Keep asking until it is up."""
        end = time.time() + patience
        last = ""
        while time.time() < end:
            try:
                w = self.ask("hello", wait=1.5).split()
            except TimeoutError:
                continue
            # a line that arrived torn (the puck's own log fighting it for the port) is asked again, not trusted
            if len(w) == 4 and w[0] == "bridge" and w[3] in ("blank", "set"):
                return {"chip": w[1], "fw": w[2], "state": w[3]}
            last = " ".join(w)
            time.sleep(0.3)
        raise RuntimeError(f"no clean hello from {self.port}" + (f" (last: {last!r})" if last else ""))

    # The link tears the odd line (see reply() in the firmware), so nothing here is trusted on one
    # reading: a set is idempotent and is repeated until its own `ok` comes back whole; a status is
    # only accepted with every key present.
    KEYS = ("wifi", "mqtt", "rssi", "sw", "light")

    def status(self, tries: int = 4) -> dict:
        for _ in range(tries):
            try:
                w = self.ask("status", wait=2.0).split()
            except TimeoutError:
                continue
            d = dict(kv.split("=", 1) for kv in w[1:] if "=" in kv)
            if all(k in d for k in self.KEYS):
                return d
        raise RuntimeError(f"no clean status from {self.port}")

    def set(self, what: str, *args: str, tries: int = 4):
        for _ in range(tries):
            try:
                r = self.ask(f"set {what} " + " ".join(args), wait=2.0)
            except TimeoutError:
                continue
            if r == f"ok {what}":
                return
            if r.startswith("err "):
                raise RuntimeError(f"puck refused {what}: {r}")
        raise RuntimeError(f"no clean answer to set {what} from {self.port}")

    def apply(self):
        r = self.ask("apply")
        if r != "ok apply":
            raise RuntimeError(f"puck refused apply: {r}")
        self.s.close()

    def wipe(self):
        r = self.ask("wipe")
        if r != "ok wipe":
            raise RuntimeError(f"puck refused wipe: {r}")
        self.s.close()


def from_header(path: str) -> dict:
    """The values a desk header compiles in, so a puck can be handed exactly what it already had."""
    text = open(path).read()
    out = {}
    for key in ("WIFI_SSID", "WIFI_PASS", "MQTT_HOST", "MQTT_USER", "MQTT_PASS", "MQTT_BASE", "DEVICE_LABEL"):
        m = re.search(rf'^#define\s+{key}\s+"(.*)"', text, re.M)
        if m:
            out[key] = m.group(1)
    m = re.search(r"^#define\s+MQTT_PORT\s+(\d+)", text, re.M)
    if m:
        out["MQTT_PORT"] = m.group(1)
    m = re.search(r"^#define\s+IV_INDEX\s+(\d+)", text, re.M)
    if m:
        out["IV_INDEX"] = m.group(1)
    for key in ("NET_KEY", "APP_KEY"):
        m = re.search(rf"{key}\[16\]\s*=\s*\{{([^}}]*)\}}", text)
        if m:
            out[key] = "".join(f"{int(b, 16):02x}" for b in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("what", choices=["hello", "status", "write", "wipe"])
    ap.add_argument("--from", dest="header")
    ap.add_argument("--wifi", nargs=2, metavar=("SSID", "PASS"))
    ap.add_argument("--mqtt", nargs=4, metavar=("HOST", "PORT", "USER", "PASS"))
    ap.add_argument("--keys", nargs=3, metavar=("NETKEY", "APPKEY", "IV"))
    ap.add_argument("--base")
    ap.add_argument("--label")
    ap.add_argument("--no-apply", action="store_true", help="write, but leave the restart to the caller")
    a = ap.parse_args()

    p = Puck(a.port)
    if a.what == "hello":
        print(p.hello())
        return
    if a.what == "status":
        p.hello()
        print(p.status())
        return
    if a.what == "wipe":
        print("wiping", p.hello())
        p.wipe()
        return

    h = from_header(a.header) if a.header else {}
    wifi = a.wifi or ((h["WIFI_SSID"], h["WIFI_PASS"]) if "WIFI_SSID" in h else None)
    mqtt = a.mqtt or ((h["MQTT_HOST"], h.get("MQTT_PORT", "1883"), h.get("MQTT_USER", ""), h.get("MQTT_PASS", "")) if "MQTT_HOST" in h else None)
    keys = a.keys or ((h["NET_KEY"], h["APP_KEY"], h.get("IV_INDEX", "0")) if "NET_KEY" in h else None)
    base = a.base or h.get("MQTT_BASE")
    label = a.label or h.get("DEVICE_LABEL")
    if not wifi:
        sys.exit("nothing to write: no --wifi and no header with one")

    who = p.hello()
    print(f"puck {who['chip']} fw {who['fw']} ({who['state']})")
    p.set("wifi", hx(wifi[0]), hx(wifi[1]));            print(f"  wifi   {wifi[0]}")
    if mqtt:
        p.set("mqtt", hx(mqtt[0]), str(mqtt[1]), hx(mqtt[2]), hx(mqtt[3])); print(f"  mqtt   {mqtt[0]}:{mqtt[1]}" + (f" as {mqtt[2]}" if mqtt[2] else ""))
    if keys:
        p.set("keys", keys[0], keys[1], str(keys[2]));   print(f"  keys   net …{keys[0][-4:]} app …{keys[1][-4:]} iv {keys[2]}")
    if base:
        p.set("base", hx(base));                          print(f"  base   {base}")
    if label:
        p.set("label", hx(label));                        print(f"  label  {label}")
    if a.no_apply:
        print("written; not applied")
        return
    p.apply()
    print("  applied; waiting for it to come back", end="", flush=True)
    time.sleep(2)
    for _ in range(30):
        try:
            q = Puck(a.port)
            who = q.hello()
            print()
            print(f"back: puck {who['chip']} fw {who['fw']} ({who['state']})")
            return
        except (TimeoutError, RuntimeError, serial.SerialException, OSError):
            print(".", end="", flush=True)
            time.sleep(1)
    print()
    sys.exit("it did not come back on the cable")


if __name__ == "__main__":
    main()
