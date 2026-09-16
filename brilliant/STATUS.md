# Brilliant switches — state of play (start here)

*Last updated 16 September 2026. This is the resume-from-here summary; the full chronological story and the
"why" behind every step is in [`../docs/brilliant.md`](../docs/brilliant.md).*

## Where we got to (all proven on a real wall switch, no Brilliant app, no reset)

The Brilliant Control panels are dead-screened but one panel's radio still works. We captured that panel's
mesh keys and can now **read and control the real wall switches directly over BLE mesh**:

| Capability | How | Status |
|---|---|---|
| Read on/off | `Generic OnOff Status` | ✅ |
| Read dim level | `Generic Level Status` | ✅ |
| Read motion (PIR) | vendor field **`0x13`** (analogue: ~2 at rest, 7–8 on walk-past) | ✅ |
| Write on/off | `Generic OnOff Set` | ✅ light obeyed |
| Write dimming | `Generic Level Set` on a **0–1000 scale** (not SIG −32768…32767) | ✅ full→2%→full, confirmed |

## The keys (the whole game)

`~/.config/brilliant-mesh/panel-net.json` (mode 600, outside the repo, `.bak` alongside). Contains:

- **netkey** `bb1ce23dad4ff4222a0198216b92578f` — network id `k3` = `3deef9825e444955` (every wall switch's netid)
- **appkey** `4275e046e4828515c87237f50299114f` — AID `0x37`
- **iv_index 7** — decryption fails silently with the wrong IV
- our provisioned unicast (`0x1a`+)

**Back this file up. Never commit it.** With it, the dead panel is irrelevant — we hold everything needed to
read and drive the mesh.

## How to run anything

Tools live in `tools/`, run with the repo venv, pointed at the panel store:

```sh
cd brilliant/tools
export BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json
V=../.venv/bin/python          # bleak + cryptography are installed here

$V census.py 12                # list live panel nodes (netid 3deef…) + signal
$V panel_sniff.py 150          # decode live on/off + dim + vendor from all switches
$V panel_poll.py 000a 150      # poll a switch's vendor fields; POLL_FIELDS=13 for motion only
$V panel_cmd.py 000a on        # control: on | off | dim:<0-100>
$V panel_cmd.py 000a dim:20
```

`PANEL_NODE=<ble-addr>` pins the proxy node (avoids weak-node roulette); otherwise the strongest is chosen.

## Known switch addresses

- **`0x000a`** — a hallway dimmer, the one we read+controlled end to end (PIR range ~5 ft)
- `0x0012` — the panel's controller element (seen polling switches; it is *not* a light)
- `0x0004`, `0x0008`, `0x000e` — other switches seen reporting
- ~8 switches total on the network; discover the rest by watching `panel_sniff.py` output for source addresses

## Gotchas already solved (don't re-discover these)

- **Proxy nonce**: octet 1 must be `0x00`, not `CTL|TTL` (fixed in `tools/mesh.py`). This is why the proxy
  forwarded nothing before — the fix is what made live reads work.
- **Dim scale is 0–1000**, not the SIG mapping. A standard-mapped level is silently ignored (the switch even
  echoes it back, looking like success). Captured by sniffing the app dim a switch.
- **Generic Level Set is command-inert for the triac on our own claimed switch** but works on panel-configured
  switches — the panel set them to dimmer mode. Don't reset a wall switch; it strips that config and we can't
  yet fully rebuild it.
- **One proxy connection per node**; the link is flaky below ~−80 dBm — reply drops are range, not logic.
- **Re-capturing keys** (only if the store is ever lost): the recorder firmware in `mesh-provisionee/` does it
  — flash it, scan a spare switch's QR in the app (QR = 16-byte UUID + 16-byte Static OOB), and it captures
  netkey + appkey. See `docs/brilliant.md` for the full recipe. The keys are already saved, so this is a
  fallback, not a needed step.

## Next task: the always-on bridge

Everything above runs from the laptop over a one-off BLE connection. To make it hub-native:

- Take `esp32-bridge/` (already does mesh proxy → MQTT for our own network) and point it at the **panel keys**.
- Decode `Generic OnOff Status`, `Generic Level Status`, and vendor field `0x13` (motion) → publish to MQTT.
- Subscribe for commands → send `Generic OnOff Set` and `Generic Level Set` (0–1000 scale) with the appkey.
- Result: three Home Assistant entities per switch (state, brightness, motion), controllable from the hub,
  with no Brilliant app or cloud in the loop.

Alternative host: the Pi with a USB BLE dongle running `bluez-meshd` (HA already owns `hci0`).

## Uncommitted work (all on disk, nothing staged)

New tools: `ble.py dim.py state.py rawlog.py vendor.py snapshot.py poll.py writable.py setfields.py
pubtest.py test_nonce.py panel_sniff.py panel_poll.py panel_cmd.py`.
Modified: `mesh.py` (proxy-nonce fix), `census.py`, `explore.py`, `listen.py`, `onoff.py`, `provision.py`.
Recorder firmware: `mesh-provisionee/src/{main.cpp,recorder.cpp,recorder.h}`.
Docs: `docs/brilliant.md`, this file. Commit when ready (secrets stay out — the keys are in `~/.config`).
