# Printers: 3D printers in the house

*Written 2 October 2026, when the brain learned to find and follow them. The wall and the phone do not show them
yet: that waits on the boards in `design/printers/`, per AGENTS.md §1.*

## The short answer

A 3D printer that runs a printer door (the Astromech door, or anything speaking its small public protocol) is a
thing the house can have, like a light. The hub finds it on the Wi-Fi, asks to be let in, somebody says yes at the
printer, and from then on the house knows what it is doing: printing, done, needs you, stopped.

## Rules that do not change

- **The hub knows printers; a printer never knows the hub.** `brain/hub/printers.py` speaks only the door's public
  protocol and imports nothing of the printer's own software. A printer with no hub loses nothing.
- **A printer lets the house in at the printer.** The hub asks (`POST /door/ask`, `kind: "hub"`, named for the
  house: *Main Palace hub*), and somebody taps Allow on the printer's own screen, or on a phone already paired with
  it at home. Asking only works from the printer's Wi-Fi. There is no code to type.
- **The panel never holds a printer's token.** The token lives in `printers.json` (mode 0600, in the backup); the
  camera and the current thumbnail reach the panel through `/printers/{id}/camera` and `/printers/{id}/thumbnail`.
- **The hub does only what a phone away may do**: pause, resume, stop, cool down, switch spools, "later". The
  printer would let the hub do more, since it is at home, but a wall in the kitchen is not somebody standing at the
  printer, which is what starting a print or saying the bed is clear needs.
- **Works with the internet down, once a printer is in.** A printer's name at home spells its LAN address
  (`192-168-86-73.obi1.home.elyir.app`), so the hub connects to that address directly and checks the certificate
  against the name: no DNS, no relay. Away is the fallback when home does not answer. Finding a printer the first
  time asks the relay which printers share the house's public address (`nearby.elyir.app`); that needs the
  internet, and nothing else depends on it.
- **The printer's words, not ours.** A printer that needs somebody is a line in *Needs a look* carrying its own
  headline ("OBI1 needs you") and detail; what it tells its phones goes in the house's log as kind `printer`.

## What the brain does

| | |
|---|---|
| `GET /printers` | `{printers: [view], found: [...], asking: {id: state}}`; also pushed as `{"type": "printers"}` on the stream |
| `POST /printers/look` | ask the relay again, now (the Add door is open) |
| `POST /printers/{id}/add` | ask the printer; the answer arrives on the stream as `asking` and then the printer |
| `DELETE /printers/{id}` | off the wall, and the hub off the printer's list of devices |
| `POST /printers/{id}/action` | `{action, args}`, the short list only (403 otherwise) |
| `GET /printers/{id}/camera[?still=1]` | the printer's camera, passed through |
| `GET /printers/{id}/thumbnail` | what it is printing |

A view is `{id, name, connected, via: home|away, state, headline, detail, actions, temps, camera, job}` with
`job = {name, progress, layer, layers, remaining_s, eta_clock, colors, material, thumbnail}`.

Checked against a real printer on 2 October 2026: found among three, asked as a hub and allowed at the printer,
followed over the Wi-Fi by address, status and temperatures and a camera frame read, a start refused, and removed
from the printer's list when forgotten.

## Not yet

- The wall and the phone: a printer on Rooms or a tab of its own, its camera in the viewer, and *found* as a knock in
  the band like a strip. Boards first.
- Notifications from the hub: the printer already tells its own paired phones; when the hub has web push (docs/
  away.md step 6), a printer the house has adopted could tell the house's phones instead. Who sends is then one
  decision, so nobody hears it twice.
