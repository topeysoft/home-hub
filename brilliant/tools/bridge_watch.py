#!/usr/bin/env python3
"""Watch what the bridge tells the broker, one line per change, per switch.

    python3 tools/bridge_watch.py [broker-host] [seconds]

Credentials come from MQTT_USER / MQTT_PASSWORD in the environment, else from
driver-layer/.env next to this repo (the hub's own broker wants the hub's .env,
not the Mac's). Walk past a switch while this runs: the `motion` line and the
`motion_level` numbers for that switch are what the bridge is reading off it.

    15:25:09  3dee/000a  brightness  128
    15:25:15  3dee/000a  brightness  255
    15:26:02  3dee/000b  motion      ON      (level 9)
    15:26:10  bridge/2e42  proxy      7c:10:15:04:de:ab rssi -74

Topics are mesh/<net>/<addr>/<leaf> and mesh/bridge/<chip>/<leaf>; the net and
chip are shortened to four hex here.
"""
import os
import sys
import time

import paho.mqtt.client as mqtt

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.86.42"
BASE = os.environ.get("MQTT_BASE", "mesh")
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 1e9
HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, "..", "..", "driver-layer", ".env")


def creds():
    u, p = os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASSWORD")
    if u and p:
        return u, p
    if os.path.exists(ENV):
        kv = dict(l.rstrip("\n").split("=", 1) for l in open(ENV) if "=" in l and not l.startswith("#"))
        return kv.get("MQTT_USER", "hub"), kv.get("MQTT_PASSWORD", "")
    return "hub", ""


last = {}
level = {}


def on_msg(_c, _u, m):
    parts = m.topic.split("/")
    if len(parts) < 4 or parts[0] != BASE:
        return
    if parts[1] == "bridge":
        who, leaf = f"bridge/{parts[2][:4]}", "/".join(parts[3:])
    else:
        who, leaf = f"{parts[1][:4]}/{parts[2]}", "/".join(parts[3:])
    val = m.payload.decode("utf-8", "replace")
    if leaf == "event":
        return                      # raw decodes; subscribe to mesh/+/+/event if you want them
    if leaf == "motion_level":
        level[who] = val
    key = (who, leaf)
    if last.get(key) == val:
        return
    last[key] = val
    extra = f"   (level {level[who]})" if leaf == "motion" and who in level else ""
    print(f"{time.strftime('%H:%M:%S')}  {who:11} {leaf:13} {val}{extra}", flush=True)


def main():
    u, p = creds()
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"bridge-watch-{os.getpid()}")
    c.username_pw_set(u, p)
    c.on_message = on_msg
    c.on_connect = lambda cl, *_: (print(f"connected to {HOST} as {u}; watching {BASE}/#"),
                                   cl.subscribe(f"{BASE}/#"))
    c.connect(HOST, 1883, 30)
    end = time.time() + SECS
    while time.time() < end:
        c.loop(1.0)


if __name__ == "__main__":
    main()
