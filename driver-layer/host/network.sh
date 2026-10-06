#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The only thing in this product that talks to NetworkManager.
#
# Two ways in, and they are the same two the update and restart paths already use:
#
#   network.sh                 write brain-data/network.json: what this hub is connected to.
#                              home-hub-network.timer runs this once a minute.
#   network.sh (with a request) brain-data/network.request appeared. home-hub-network.path starts
#                              this, it does the one thing the file asks for, and deletes it.
#
# THE REQUEST NAMES A VERB AND NEVER A COMMAND. Four of them -- scan, join, forget, off -- checked
# again below against a list written here rather than sent from there. An SSID and a password are
# DATA: they are read into shell variables and handed to nmcli as single arguments, never evaluated,
# never concatenated into a command line. update.sh makes the same point about the version it is
# handed and restart.sh about the rung; keep the three shaped alike so a reader of one recognizes
# the others.
#
# WHAT THIS NEVER WRITES IS A PASSWORD. network.json rides the backup and is read by anything that
# can read the data volume; NetworkManager already keeps the PSK at 0600 under /etc and there is no
# reason for a second copy. The brain holds whatever was typed at the panel and knows it might be
# for a different network -- that is bridge.wifi_for_pucks()'s whole job.
#
# Safe to run by hand.
set -uo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
DL="$DIR/driver-layer"; DATA="$DL/brain-data"
REQ="$DATA/network.request"; STATE="$DATA/network.json"; LOG="$DATA/network.log"
# How long a new connection has to prove itself before this puts the old one back. Long enough for
# DHCP on a slow router, short enough that nobody has gone to find a keyboard.
SETTLE="${HOME_HUB_NETWORK_SETTLE:-180}"

have() { command -v "$1" >/dev/null 2>&1; }
say() { echo "$(date -Is) $*" >> "$LOG"; }

# ---------------------------------------------------------------- what is true now

# nmcli's terse output, one field, for one device.
dev_field() { nmcli -t -g "$1" device show "$2" 2>/dev/null | head -1; }

write_state() {
  local tmp="$STATE.tmp" first=1
  {
    printf '{"at": %s, "hostname": "%s", "links": [' "$(date +%s)" "$(hostname -s 2>/dev/null || echo hub)"
    # Every wired and wireless device NetworkManager admits to, with what it is doing. A device that
    # is present but down still belongs here: "this hub has a radio and is not using it" is a
    # different sentence from "this hub has no radio", and the panel has to tell them apart.
    while IFS=: read -r name type state _; do
      [ -n "$name" ] || continue
      local kind
      case "$type" in ethernet) kind=ethernet ;; wifi) kind=wifi ;; *) continue ;; esac
      local up=false ip="" ssid="" signal="" band=""
      [ "$state" = "connected" ] && up=true
      ip="$(dev_field IP4.ADDRESS "$name" | cut -d/ -f1)"
      if [ "$kind" = wifi ]; then
        # The line nmcli marks with a * is the one this device is actually on.
        local row
        row="$(nmcli -t -f IN-USE,SSID,SIGNAL,FREQ device wifi list ifname "$name" 2>/dev/null | grep '^\*' | head -1)"
        ssid="$(echo "$row" | cut -d: -f2)"
        signal="$(echo "$row" | cut -d: -f3)"
        case "$(echo "$row" | cut -d: -f4)" in 5*|6*) band=5 ;; 2*) band=2.4 ;; esac
      fi
      [ $first -eq 1 ] || printf ','
      first=0
      printf '{"kind":"%s","device":"%s","up":%s,"ip":"%s"' "$kind" "$name" "$up" "$ip"
      [ -n "$ssid" ] && printf ',"ssid":%s' "$(json_str "$ssid")"
      [ -n "$signal" ] && printf ',"signal":%s' "$signal"
      [ -n "$band" ] && printf ',"band":"%s"' "$band"
      printf '}'
    done < <(nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>/dev/null)
    printf ']'
    # Anything the last scan found, and anything the last join is still being judged on, are kept
    # across a state write: they are slower-moving facts than a link's IP and re-deriving them every
    # minute would mean scanning every minute.
    [ -f "$DATA/network.scan" ] && printf ', "scan": %s, "scanned": %s' "$(cat "$DATA/network.scan")" "$(stat -c %Y "$DATA/network.scan" 2>/dev/null || stat -f %m "$DATA/network.scan")"
    [ -f "$DATA/network.moving" ] && printf ', "moving": %s' "$(cat "$DATA/network.moving")"
    [ -f "$DATA/network.reverted" ] && printf ', "reverted": %s' "$(json_str "$(cat "$DATA/network.reverted")")"
    printf '}\n'
  } > "$tmp" 2>/dev/null && mv "$tmp" "$STATE"
}

# A shell string into a JSON string, without pulling in a JSON library for four values. An SSID may
# contain a quote, a backslash or a stray byte, and a state file that will not parse is a panel that
# says the hub has no network at all.
json_str() { printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || printf '""'; }

scan() {
  nmcli device wifi rescan >/dev/null 2>&1
  sleep 4
  nmcli -t -f SSID,SIGNAL,FREQ,SECURITY device wifi list --rescan no 2>/dev/null | python3 -c '
import json, sys
out, seen = [], set()
for line in sys.stdin:
    # nmcli escapes a colon inside a field as \:, so unescape before splitting on the real ones.
    parts, cur, esc = [], "", False
    for ch in line.rstrip("\n"):
        if esc: cur += ch; esc = False
        elif ch == "\\": esc = True
        elif ch == ":": parts.append(cur); cur = ""
        else: cur += ch
    parts.append(cur)
    if len(parts) < 4 or not parts[0] or parts[0] in seen: continue
    seen.add(parts[0])
    try: signal = int(parts[1])
    except ValueError: signal = None
    freq = parts[2].split()[0] if parts[2] else ""
    out.append({"ssid": parts[0], "signal": signal,
                "band": "5" if freq[:1] in ("5", "6") else "2.4" if freq[:1] == "2" else None,
                "secure": parts[3].strip() not in ("", "--")})
print(json.dumps(out))' > "$DATA/network.scan.tmp" 2>/dev/null \
    && mv "$DATA/network.scan.tmp" "$DATA/network.scan"
}

# ---------------------------------------------------------------- moving this hub

# Did it actually work? Not "is the brain answering" -- the brain is on the host's loopback and
# answers perfectly well on a machine with no network at all, which is exactly the failure this is
# supposed to catch. The test is the network's own: the device is connected, it has an address, and
# something at the other end of the wire answers.
came_up() {
  local dev="$1" deadline=$(( $(date +%s) + SETTLE ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if [ "$(dev_field GENERAL.STATE "$dev" | cut -d' ' -f2 | tr -d '()')" = "connected" ]; then
      local gw; gw="$(dev_field IP4.GATEWAY "$dev")"
      if [ -n "$(dev_field IP4.ADDRESS "$dev")" ] && [ -n "$gw" ] && ping -c1 -W3 "$gw" >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 5
  done
  return 1
}

join() {
  local ssid="$1" pass="$2"
  local dev; dev="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')"
  if [ -z "$dev" ]; then say "join: this machine has no wireless device"; return 1; fi
  # What to go back to. A hub on a cable has nothing to lose here and this is empty, which is the
  # right answer: adding Wi-Fi to a wired hub cannot strand it and must not pretend it can.
  local was; was="$(nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null | awk -F: -v d="$dev" '$2==d{print $1; exit}')"
  printf '{"ssid": %s, "since": %s}' "$(json_str "$ssid")" "$(date +%s)" > "$DATA/network.moving"
  rm -f "$DATA/network.reverted"
  write_state
  say "join: $ssid on $dev (was: ${was:-nothing})"

  # The password reaches nmcli as one argument and is never evaluated. It is briefly visible in the
  # process list, which on this machine means visible to root, which is what is running this script.
  nmcli device wifi connect "$ssid" password "$pass" ifname "$dev" >/dev/null 2>&1

  if came_up "$dev"; then
    say "join: $ssid came up"
    rm -f "$DATA/network.moving"
  else
    # The case this whole script exists for. Nothing reached the far end, so put back whatever was
    # working and say which network did not take -- the panel needs to name it.
    say "join: $ssid did not come up in ${SETTLE}s; putting back ${was:-the previous connection}"
    nmcli connection delete "$ssid" >/dev/null 2>&1
    [ -n "$was" ] && nmcli connection up "$was" >/dev/null 2>&1
    printf '%s' "$ssid" > "$DATA/network.reverted"
    rm -f "$DATA/network.moving"
  fi
  write_state
}

forget() {
  local ssid="$1"
  [ -n "$ssid" ] || return 1
  nmcli connection delete "$ssid" >/dev/null 2>&1
  say "forget: $ssid"
}

# ---------------------------------------------------------------- the one thing being asked

if ! have nmcli; then
  # Not a failure worth a log line every minute: it is a permanent property of this machine, and the
  # brain reads the absence of network.json as "nobody can change this from here" and says so.
  exit 0
fi

if [ -f "$REQ" ]; then
  DO="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("do",""))' "$REQ" 2>/dev/null)"
  SSID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("ssid",""))' "$REQ" 2>/dev/null)"
  PASS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("password",""))' "$REQ" 2>/dev/null)"
  rm -f "$REQ"
  case "$DO" in
    scan)   scan ;;
    join)   join "$SSID" "$PASS" ;;
    forget) forget "$SSID" ;;
    off)    nmcli radio wifi off >/dev/null 2>&1; say "radio off" ;;
    *)      say "not a thing this hub knows how to do: ${DO:-<nothing>} -- nothing done" ;;
  esac
fi

write_state
