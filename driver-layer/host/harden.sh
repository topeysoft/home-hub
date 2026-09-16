#!/usr/bin/env bash
# The host as an appliance. Three things a box in somebody else's house needs that a developer's box
# does not, each one file, each written only when it differs from what is there:
#   1. a hardware watchdog, so a hung kernel reboots itself instead of waiting for a person with ssh;
#   2. a cap on every container's log, so a chatty Zigbee network cannot fill a 32 GB eMMC;
#   3. a cap on the system journal, for the same reason.
# install.sh runs this as root on every install and update. Exit 10 means the log cap is new and the
# containers have to be made again to take it (install.sh does that once); anything else non-zero is
# a real failure. Nothing here is Pi-specific except turning the Pi's watchdog on when it is off.
set -euo pipefail
have() { command -v "$1" >/dev/null 2>&1; }
put() {  # put <file> <content>: write when different; true when written
  local f="$1" body="$2"
  if [ -f "$f" ] && [ "$(cat "$f")" = "$body" ]; then return 1; fi
  mkdir -p "$(dirname "$f")"; printf '%s\n' "$body" > "$f"
}
recreate=0

# 1. The watchdog. systemd pets it; if the kernel stops answering for 30 s the board resets. A box
#    with no watchdog device (a VM, some mini PCs) gets a warning in the journal and nothing else.
if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null && [ ! -e /dev/watchdog ]; then
  CFG=/boot/firmware/config.txt; [ -f "$CFG" ] || CFG=/boot/config.txt
  if [ -f "$CFG" ] && ! grep -q '^dtparam=watchdog=on' "$CFG"; then
    printf '\n# home-hub: hardware watchdog (host/harden.sh)\ndtparam=watchdog=on\n' >> "$CFG"
    echo "  watchdog: turned on in config.txt (takes effect on the next boot)"
  fi
fi
if put /etc/systemd/system.conf.d/home-hub.conf "$(printf '[Manager]\nRuntimeWatchdogSec=30s\nRebootWatchdogSec=5min')"; then
  have systemctl && systemctl daemon-reexec >/dev/null 2>&1 || true
  echo "  watchdog: systemd pets it every 30 s"
fi

# 2. Container logs: 10 MB, three of them, per container. json-file is Docker's default driver and
#    the one `docker logs` reads, so nothing about debugging changes. daemon.json is merged, not
#    replaced: a box that already had one keeps what was in it.
if have python3; then
  if [ "$(python3 - <<'PY'
import json, os
p = "/etc/docker/daemon.json"
d = {}
if os.path.exists(p):
    try:
        d = json.load(open(p))
    except Exception:
        d = {}
want = {"max-size": "10m", "max-file": "3"}
opts = d.get("log-opts") if isinstance(d.get("log-opts"), dict) else {}
same = d.get("log-driver", "json-file") == "json-file" and all(opts.get(k) == v for k, v in want.items())
if not same:
    d["log-driver"] = "json-file"
    d["log-opts"] = {**opts, **want}
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2); f.write("\n")
    os.replace(tmp, p)
print("same" if same else "changed")
PY
)" = "changed" ]; then
    # The daemon reads this at start; the cap reaches a container when it is next created.
    have systemctl && systemctl restart docker >/dev/null 2>&1 || true
    echo "  logs: capped at 10 MB x 3 per container"
    recreate=1
  fi
else
  echo "  logs: python3 is missing, so the container log cap was not written"
fi

# 3. The journal. 200 MB on disk, 50 MB in memory before it gets there.
if put /etc/systemd/journald.conf.d/home-hub.conf "$(printf '[Journal]\nSystemMaxUse=200M\nRuntimeMaxUse=50M')"; then
  have systemctl && systemctl restart systemd-journald >/dev/null 2>&1 || true
  echo "  journal: capped at 200 MB"
fi

[ "$recreate" = 1 ] && exit 10
exit 0
