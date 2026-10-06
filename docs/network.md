# The network the house runs on

*Written 18 September 2026. **Pieces 1 to 5 and 7 were built the same day** — see *What landed* at the
foot; piece 6 is still a plan. It covers one thing — how the hub is connected, and what
follows it when that changes. The goal it serves is the same as every other document here: nobody who receives a
hub ever opens Home Assistant, a terminal, or a support article. A household that changes its Wi‑Fi password
should not have to go around the house collecting hardware.*

## What was true before this (18 September 2026)

The hub was designed on a cable, and the cable hid four things. All four are fixed; they are left
written down here because the argument for the shape below is made of them.

- **The hub has no network configuration path at all.** `install.sh` names the machine and starts avahi so
  `hub.local` resolves; nothing anywhere configures `wlan0`. Whatever the image was flashed with is what the
  household has, for the life of the hub. Putting a hub on Wi‑Fi means re-flashing a card.
- **The Wi‑Fi the hub hands out is a typed copy, never re-checked.** `Bridges.wifi()` takes an SSID and password
  from `POST /bridge/wifi` and puts them in settings; `Bridges.config()` reads that back for every puck it ever
  writes. Nothing compares it to reality. Change the house password and the hub will keep writing the old one
  into every new puck, and finish with a green tick.
- **The broker address handed to a puck is a raw DHCP lease.** `config()` sends `lan_ip()` — a number — and the
  firmware calls `mqtt.setServer()` with it. There is no mDNS anywhere in the firmware. A router reboot that
  reshuffles the pool strands every puck in the house *without anybody touching the Wi‑Fi at all*. The hub
  already publishes itself as `hub.local`; the pucks are the one thing on the network that ignores it.
- **There is no way back but the cable.** `set wifi` exists only on the USB line. A configured puck with wrong
  credentials sits in `WiFi.setAutoReconnect(true)` forever — no fallback, no return to the blank waiting state.
  Its light goes amber, which is honest and unactionable. Recovery is: unplug every puck in the house, carry
  them to the hub, cable each one.

Those are four bugs with one cause. **The hub hands out what it was told instead of what it is using**, and
nothing in the system can correct a thing once it has been told wrong.

## The rule this document adds

> **The hub gives a puck what the hub is using, and everything it gives can be corrected without a cable.**

Two halves. The first deletes the class of bug where the hub is confidently wrong. The second decides that a
credential is not a fact carved into a device at birth — it is a thing the house can change its mind about.

## Piece 1: a name, not a number

The cheapest fix and the one that removes the likeliest failure, so it goes first and nothing depends on it.

A puck is told **both** the hub's name and its address, and it tries three things in order:

1. `hub.local`, resolved by mDNS.
2. The last address that actually worked, kept in its own NVS.
3. The address it was given at setup.

Any success overwrites (2). That is self-healing in both directions: a DHCP reshuffle is caught by (1), and a
house where mDNS is broken — some mesh routers filter multicast — is caught by (2) and (3). Neither failure
needs a person.

The hostname is not assumed. `install.sh` sets `hub`, but a second hub on the same LAN becomes `hub-2`, so the
hub sends **the name it actually answers to**, read at the moment it writes the puck, exactly as piece 2
requires of everything else.

## Piece 2: the hub stops being told its own network

The brain learns to answer four questions about itself: *on a cable or on Wi‑Fi, which network, how good is it,
what address*. Then `Bridges.config()` stops reading a typed field and starts reading that.

- **A hub on Wi‑Fi hands out the credentials it is itself using.** One source of truth. It cannot be stale,
  because if it were stale the hub would not be on the network to say so.
- **A hub on a cable still has to be told**, and that is the one legitimate use of the typed field. But the
  panel must then say what it is: not *the house's Wi‑Fi* but **the Wi‑Fi the bridges use** — with the hub
  admitting it cannot check it. A sentence the hub cannot verify should be phrased as one it cannot verify.
- **The brain does not configure the host.** It reads `network.json` and writes `network.request`; a path unit
  runs `network.sh`, which is the only thing that talks to NetworkManager. This is `updates.py`'s rule and
  `restart.sh`'s shape, unchanged: **the request names a thing from a fixed list, never a command.** A request
  file that could carry an `nmcli` argument list would turn "can write the data volume" into "can run anything
  as root".

## Piece 3: two keys on the ring

This is the piece that makes a Wi‑Fi change survivable, and it is smaller than it sounds.

**A puck holds two credential sets, not one.** The one it is using, and the one it used before. When it cannot
reach a network, it alternates between them every two minutes, forever.

Everything else falls out of that:

- **Order stops mattering.** It does not matter whether the hub moves first or the pucks do. Whoever arrives
  second finds the other already there.
- **A typo is not fatal.** Push a wrong password to eleven pucks and every one of them is back on the old
  network within four minutes. The house repairs itself while somebody works out what they mistyped.
- **A change of mind is free.** Move the hub to the new router, decide against it, move back — the pucks follow
  both ways without being touched.
- **The old key is dropped only on proof.** A puck keeps the previous set until the hub has seen it online on
  the new network and says *you can forget the other one*. Not on a timer, and not by the puck's own judgment:
  a puck that is online cannot tell whether the hub can see it.

The channel this rides on already exists in shape: `<base>/bridge/<chip>/claim` is a per-puck command topic that
queues onto the loop and answers on a sibling topic. Network config is a second verb on that same pattern —
`<base>/bridge/<chip>/net` in, `.../net/state` back. **`docs/puck-updates.md` needs exactly this channel too,
and neither document should build its own.** Whichever ships first builds the channel; the second adds a verb.

## Piece 4: the hub's own move

Changing the hub's network is, like restarting, an action that destroys the thing being used to perform it —
except that unlike a restart, it can fail in a way that never comes back on its own. So it inherits the restart
design's answer and hardens it.

- **Confirm or revert, always.** The host applies the new connection, then watches for the brain to be reachable
  and *stay* reachable. If nothing has reached it in three minutes, it puts the previous connection back. This
  is `update.sh`'s rollback, pointed at a different kind of failure, and it is what makes the button safe to
  offer at all.
- **Ethernet is never given up.** A hub with a cable that is also given Wi‑Fi keeps both; the cable wins while it
  is there and the Wi‑Fi is a spare. Nothing about adding Wi‑Fi should be able to take a working hub off the
  network, and a household that adds it "just in case" has done something sensible rather than something risky.
- **The cable stays the recommendation, and the reason is named.** Not because the hub's own reception is poor —
  because on a Pi, Wi‑Fi and Bluetooth share one radio, and a hub that is doing Bluetooth work while its Wi‑Fi
  is busy does both worse. So: allow Wi‑Fi, prefer 5 GHz where the host can, and say the sentence once in the
  sheet rather than burying it.
- **A change to the network is a change to the house.** `needs_code()` gains the route, and `holds_keys()` gates
  it, for the reason restart does: a guest phone admitted for the weekend may run the house and may not take it
  off the network.
- **Not from away.** This is the one place this document refuses something the restart design allowed. A restart
  away from home is caught by a watchdog on the machine; a Wi‑Fi change away from home can be right and still
  leave nobody able to confirm it. The away phone gets a sentence, not a form: *Changing the network has to be
  done in the house.*

## Piece 5: the hub with no network at all

A Wi‑Fi-only hub on first boot, and a Wi‑Fi-only hub whose network has gone, are the same situation: there is
nothing to reach it on. The floor is a **setup network of its own** — `Home Hub setup`, no password, the panel
at a fixed address on it, one screen asking which Wi‑Fi.

Two rules keep it from becoming a liability:

- **It exists only when nothing else does.** The moment the hub has a working connection the AP is gone. A hub
  quietly running an open access point in the corner of somebody's house is a security problem the household did
  not agree to.
- **It is the same panel, not a second one.** The setup screen already exists (`Setup.vue`); this is one more
  step in front of it, with the same words and the same look. A separate captive-portal page written once and
  never loved again is how this feature rots.

## Piece 6: the ones that did not follow

Perfection is not available. A puck that was unplugged during the change, or is on a socket at the edge of
range, will miss it. The design's job is to make that a short, named list rather than a mystery.

- **The panel names them, by room.** Not *3 bridges did not respond* — *The one in the hallway and the one in
  the back bedroom.* The household knows where those are; a chip id tells them nothing.
- **Their recovery is the cable, and the sheet says so plainly.** One sentence: *Bring it to the hub and plug it
  in; it takes a minute.* No apology, no support article.
- **A puck that has been gone a day becomes a job.** `health.py` already turns quiet things into *Needs a look*
  lines with acts on them. A bridge that has not been heard from since the network changed is exactly that, and
  it should carry the sentence above as its act.

## Piece 7: where this lives in the panel

*This hub* gains one row, in the same three-column shape as Software, Backup, Restore and Restart:

> **Network** — On your Wi‑Fi, *Upstairs*. Strong.  *[Change]*

or, for the hub this product was designed for:

> **Network** — On a cable. Bridges use *Upstairs*.  *[Change]*

One row, one button, and the ladder behind it — exactly the restart design's argument. The person is not asked
to choose between *configure the hub's interface* and *set the credentials handed to peripherals*; those are the
same sentence to a household, and the hub works out which parts of it changed.

The change flow is four screens and they are drawn before they are built (`design/network/`): what we are on
now, which network to move to, the moment of the move with its countdown, and what followed. The fourth screen
is the one this whole document exists for and it must not be skipped when nothing went wrong — *All eleven
bridges followed* is the sentence that teaches a household this is safe to do.

## Order

1. **Piece 1, the name.** Firmware mDNS with the last-good address behind it, and the hub sending its real
   hostname. Independent of everything below, and it removes the failure that will actually happen first.
2. **Piece 2, the hub reading itself.** `network.json`, the brain's reader, the *Network* row on *This hub*
   showing the truth. Read-only: no button yet. A hub that can describe its own network is worth shipping on
   its own, and every piece below needs it.
3. **Piece 3, two keys on the ring.** The `net` verb on the per-puck channel, and the firmware holding two sets.
   Before any UI can change a credential, the thing being changed has to be able to survive it.
4. **Piece 4's flow, for the credentials only.** Changing what the bridges use, from the panel, with the
   following-and-who-did-not screen. Still no change to the hub's own connection — this is the common case
   (the household changed its router password) and it is safe once 3 exists.
5. **Piece 4's own move.** `network.sh`, confirm-or-revert, the hub joining a Wi‑Fi from the panel. Last of the
   main line, because it is the one that can strand a house, and it should not exist before the thing that
   catches it.
6. **Piece 5, the setup AP.** Needed the day a hub ships without an ethernet port; not before.
7. **Piece 6's health job.** A bridge that never came back becomes a line on Home with the cable sentence on it.

## What landed, 18 September 2026

Pieces 1 to 5 and 7, in the order above.

- **The name.** A puck is given the hub's hostname alongside its address (`Bridges.config`,
  `puck_cable.py --name`) and resolves mDNS first, the last address that answered second, the one it
  was given third — `hubAddress()` in `main.cpp`, with whatever works written to NVS by
  `configRemember()`. `hubTry` moves on after each failed attempt, so a name that resolves to
  something stale cannot pin a puck to a dead address.
- **The hub reading itself.** `hub/network.py` from `network.json`; `driver-layer/host/network.sh`
  and its path unit, service and one-minute timer; the *Network* row on *This hub*.
  `Bridges.wifi_for_pucks()` is where the original bug dies: a hub on Wi‑Fi hands out the network it
  is on, and a password held for a different network is not handed out at all.
- **Two keys on the ring.** `cfg.ssid2`/`pass2` in NVS, `wifiTick()` alternating every two minutes,
  `configConfirmWifi()` writing down whichever won. The command topic is `<base>/bridge/<chip>/cfg`
  (hex-encoded words like `claim`, queued onto the loop, retained) answered on `.../cfgack`, which is
  proof rather than a promise: a puck cannot publish from a network it never joined.
- **The bridges' move, from the panel.** `POST /network/bridges`, `Bridges.move()`, and
  `app/src/NetworkSheet.vue` drawn from `design/network/`. Every known puck is told, because the
  command is retained and one that was switched off collects it when it comes back; only the ones
  listening are counted while somebody stands at the wall.
- **The hub's own move.** `POST /network/hub` tells the bridges first and the host second;
  `network.sh` watches the new connection reach its gateway for three minutes and puts the old one
  back otherwise. Gated by `needs_code()` and refused from away.
- **The ones that never came back.** `Bridges._saw()` stamps the moment a bridge goes quiet into
  settings, `Bridges.quiet()` decides when that is worth saying — a day for one simply gone, two
  hours for one that missed a move, which is as long as the self-healing needs — and
  `Health.bridges()` turns it into a line on Home. The line says the switches still work before it
  says anything else, because a household whose panel has stopped showing the hallway will walk to
  the switch, find it works, and distrust the panel. The recovery is a walk to a socket, so it is in
  the sentence and not in a button; the one act is `POST /bridge/forget`, which clears the retained
  topics too, or a bridge forgotten on Monday is back in the list on Tuesday.

### Still a plan

- **Piece 6, the setup AP.** Needed the day a hub ships without an ethernet port. A Wi‑Fi-only hub
  with no network is, until then, a hub somebody flashed a card for.
- **What went quiet with it.** A bridge's line does not yet gather its own switches into `with`, the
  way a dead radio gathers the devices behind it. Whether a mesh light actually goes `unavailable`
  when its bridge stops publishing has not been checked, and claiming it without checking would put
  a fault's name on devices that are fine.
- **Naming a bridge.** `Bridges.where()` uses a room only when one puck carries a mesh on its own,
  and says *A bridge* otherwise rather than putting a name on the wrong object. The real fix is for
  the placing step to record where somebody just put it — one question, on a screen that already
  exists, and it wants its own board.
