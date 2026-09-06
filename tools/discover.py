#!/usr/bin/env python3
"""Seed the device inventory from what the LAN advertises right now.

Runs on macOS (uses /usr/bin/dns-sd) with no third-party packages.
Browses every mDNS service type present, resolves each instance, sends an
SSDP M-SEARCH, and writes docs/inventory.draft.md plus a JSON dump.

    python3 tools/discover.py [--seconds 3]
"""
import argparse, json, re, socket, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

# Service types that identify a vendor or protocol. Anything else is still listed.
KNOWN = {
    "_hue._tcp": ("Philips Hue bridge", "Wi-Fi/Zigbee via bridge", "local API"),
    "_googlecast._tcp": ("Google Cast / Nest", "Wi-Fi", "local for cast, cloud for Nest devices"),
    "_matter._tcp": ("Matter device (operational)", "Matter over Wi-Fi/Thread", "local"),
    "_matterc._udp": ("Matter device (commissionable)", "Matter", "local, not yet commissioned"),
    "_hap._tcp": ("HomeKit accessory", "Wi-Fi/Thread", "local via HomeKit controller"),
    "_homekit._tcp": ("HomeKit hub", "Wi-Fi", "Apple"),
    "_airplay._tcp": ("AirPlay", "Wi-Fi", "local"),
    "_raop._tcp": ("AirPlay audio", "Wi-Fi", "local"),
    "_shelly._tcp": ("Shelly", "Wi-Fi", "local"),
    "_esphomelib._tcp": ("ESPHome", "Wi-Fi", "local"),
    "_ewelink._tcp": ("Sonoff eWeLink", "Wi-Fi", "local LAN mode"),
    "_sonos._tcp": ("Sonos", "Wi-Fi", "local"),
    "_spotify-connect._tcp": ("Spotify Connect", "Wi-Fi", "local"),
    "_amzn-wplay._tcp": ("Amazon Echo/Fire", "Wi-Fi", "cloud"),
    "_ipp._tcp": ("Printer", "Wi-Fi", "local"),
    "_moonraker._tcp": ("Klipper/Moonraker", "Wi-Fi", "local"),
    "_octoprint._tcp": ("OctoPrint", "Wi-Fi", "local"),
    "_meshcop._udp": ("Thread border router", "Thread", "local"),
    "_openthread._udp": ("Thread border router", "Thread", "local"),
    "_wled._tcp": ("WLED", "Wi-Fi", "local"),
    "_tplink._tcp": ("TP-Link Kasa/Tapo", "Wi-Fi", "local"),
    "_dyson_mqtt._tcp": ("Dyson", "Wi-Fi", "local MQTT"),
    "_roborock._tcp": ("Roborock", "Wi-Fi", "cloud"),
    "_nanoleafapi._tcp": ("Nanoleaf", "Wi-Fi", "local"),
    "_elg._tcp": ("Elgato Key Light", "Wi-Fi", "local"),
    "_tedapi._tcp": ("Tesla Powerwall / Gateway", "Wi-Fi", "local TEDAPI + cloud"),
    "_androidtvremote2._tcp": ("Android TV / Google TV", "Wi-Fi", "local remote protocol"),
    "_matterd._udp": ("Matter commissioner (a hub/speaker acting as controller)", "Matter", "n/a"),
    "_workstation._tcp": ("Linux host", "Wi-Fi/Ethernet", "ssh"),
    "_roku-ecp._tcp": ("Roku", "Wi-Fi", "local ECP"),
}


def run(args, seconds):
    """Run dns-sd for a fixed time and return its stdout lines."""
    try:
        p = subprocess.run(["dns-sd", *args], capture_output=True, text=True, timeout=seconds)
        out = p.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    return out.splitlines()


def service_types(seconds):
    """Columns: Timestamp A/R Flags if Domain Service-Type Instance-Name, e.g. '_tcp.local.  _ssh'."""
    types = set()
    for line in run(["-B", "_services._dns-sd._udp", "local."], seconds):
        if " Add " not in line:
            continue
        parts = line.split(None, 6)
        if len(parts) == 7 and parts[5].startswith(("_tcp", "_udp")):
            types.add(f"{parts[6].strip()}.{parts[5].split('.')[0]}")
    return sorted(types)


def instances(stype, seconds):
    names = set()
    for line in run(["-B", stype, "local."], seconds):
        if " Add " not in line:
            continue
        # columns: Timestamp A/R Flags if Domain Service Type Instance Name
        parts = line.split(None, 6)
        if len(parts) == 7:
            names.add(parts[6].strip())
    return sorted(names)


def resolve(stype, name, seconds):
    host, port, txt = None, None, {}
    for line in run(["-L", name, stype, "local."], seconds):
        m = re.search(r"can be reached at (\S+?):(\d+)", line)
        if m:
            host, port = m.group(1), int(m.group(2))
        if line.strip() and "=" in line and "can be reached" not in line and "Lookup" not in line:
            for kv in re.findall(r"(\w[\w.-]*)=([^\s]*)", line):
                txt[kv[0]] = kv[1]
    return host, port, txt


def ssdp(seconds):
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           "MAN: \"ssdp:discover\"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.settimeout(0.5)
    s.sendto(msg, ("239.255.255.250", 1900))
    found = {}
    end = time.time() + seconds
    while time.time() < end:
        try:
            data, addr = s.recvfrom(4096)
        except socket.timeout:
            continue
        hdrs = dict(re.findall(r"^([\w-]+):\s*(.*?)\r?$", data.decode(errors="ignore"), re.M | re.I))
        hdrs = {k.upper(): v for k, v in hdrs.items()}
        key = (addr[0], hdrs.get("USN", ""))
        found[key] = {"ip": addr[0], "server": hdrs.get("SERVER", ""), "location": hdrs.get("LOCATION", ""), "st": hdrs.get("ST", "")}
    return list(found.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=3.0, help="browse time per service type")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs"))
    a = ap.parse_args()

    types = service_types(a.seconds)
    print(f"{len(types)} mDNS service types on the LAN", file=sys.stderr)
    devices = []
    for st in types:
        for name in instances(st, a.seconds):
            host, port, txt = resolve(st, name, min(a.seconds, 2.0))
            devices.append({"service": st, "name": name, "host": host, "port": port, "txt": txt})
            print(f"  {st:28s} {name}", file=sys.stderr)
    upnp = ssdp(a.seconds)
    print(f"{len(upnp)} SSDP responders", file=sys.stderr)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "discovery.json").write_text(json.dumps({"scanned": time.strftime("%Y-%m-%d %H:%M"), "mdns": devices, "ssdp": upnp}, indent=2))

    by_host = defaultdict(list)
    for d in devices:
        by_host[d["host"] or d["name"]].append(d)

    lines = ["# Inventory draft (auto-generated)", "",
             f"Scanned {time.strftime('%Y-%m-%d %H:%M')} from this Mac. Copy rows you keep into inventory.md and fill in room and decision.", "",
             "| Host | Advertised as | Looks like | Protocol | Control path |", "|---|---|---|---|---|"]
    for host, ds in sorted(by_host.items()):
        kinds = sorted({d["service"] for d in ds})
        known = [KNOWN[k] for k in kinds if k in KNOWN]
        label, proto, path = known[0] if known else ("?", "?", "?")
        names = "; ".join(sorted({d["name"] for d in ds}))[:80]
        lines.append(f"| {host} | {names} | {label} | {proto} | {path} |")
    lines += ["", "## SSDP / UPnP responders", "", "| IP | Server | Location |", "|---|---|---|"]
    seen = set()
    for u in upnp:
        k = (u["ip"], u["server"], u["location"])
        if k in seen:
            continue
        seen.add(k)
        lines.append(f"| {u['ip']} | {u['server'][:60]} | {u['location']} |")
    lines += ["", "## Not discoverable this way (add by hand)", "",
              "- Z-Wave devices: only visible once a Z-Wave stick is running. List from the old hub's app.",
              "- Zigbee devices on the Hue bridge: list via the bridge API once paired (tools/hue_inventory.py, later).",
              "- Ring, Brilliant, Wink, Google Nest cloud devices: list from their apps.", ""]
    (out / "inventory.draft.md").write_text("\n".join(lines))
    print(f"wrote {out/'inventory.draft.md'} and discovery.json", file=sys.stderr)


if __name__ == "__main__":
    main()
