# Rescue: keeping a wall panel after the company goes

*Written 17 September 2026, from the correction that reframed `docs/brilliant.md`: this is not only about the
two dead panels in this house. It is about everybody whose panel **still works** — those whose ecosystem is
dying (Brilliant owners now, Wink Relay owners since 2020, and whoever is next), and those whose ecosystem is
fine but who would rather their hallway light did not depend on somebody else's servers. Both cases are the
opposite of ours, and both are much easier. What is settled here is the shape; the per-device checks at the foot
are not done yet, and this document is careful about which is which.*

## The case, and why it is not the one this repo has been solving

`docs/brilliant.md` took the hard road — rebuild the mesh from scratch, capture the keys by being provisioned,
reverse the vendor store one field at a time — for one reason: **both panels here are dead**, so the panel's own
software was never available to ask. That is the worst starting position of anyone who owns this hardware.

Almost nobody else is in it. Their screen lights up. Their panel is a working Android computer on their Wi-Fi
that the manufacturer has already left. Everything this house had to earn, their panel will hand over.

**The timing is why the question is live.** Brilliant ran out of money and laid off all staff in May 2024, was
revived as Brilliant NextGen, and in July 2026 launched *Brilliant Max* — a subscription that turns the system
into a managed service. Wink's ecosystem went behind a subscription and then dark years earlier. Neither owner
did anything wrong, and both are looking at a light switch that needs somebody else's servers.

### Not everybody arriving here has lost anything

A second person matters at least as much as the first, and is probably the larger group: **nothing of theirs is
broken.** The panel lights up, the app works, the subscription is affordable. They simply do not want the lamp in
their hallway to depend on a company's servers, and they would rather their Brilliant hardware lived on a local
network they run — their own Home Assistant, or a hub like this one.

That is an ordinary preference, not an emergency, and it changes what the tooling has to be:

| | **Rescue** | **Migrate** |
|---|---|---|
| What happened | The company left, or is leaving | Nothing. It all still works |
| What they feel | Stranded | Unwilling to be, later |
| When they act | When it breaks — too late for some paths | Whenever. Which usually means never, without a reason |
| What they will accept | Quite a lot; the alternative is a brick | Very little. It has to be better than what works today |
| What they need | A way back in | A way out, with nothing lost on the way |

The migrating owner is the demanding one. A rescue only has to beat a dead panel. A migration has to beat a
product that is, at that moment, working fine — and the moment it costs them a dimmer, a three-way position or a
motion sensor that used to work, they put the screwdriver down and tell people it was not worth it.

**This is also the case this house has actually proved.** The stairway pair here runs on our own network, switch
to switch, with the panel and the hub out of the path (`docs/brilliant.md`). Nothing about that needed Brilliant
to be dead — it is a migration, done for its own sake, and it works.

**And the destination does not have to be us.** `brilliant/esp32-bridge` speaks MQTT, and everything in
`docs/brilliant.md` — the provisioner, the adopt spec, the vendor-field map, the pairing rules for multi-way — is
hub-agnostic. Somebody with plain Home Assistant and no intention of ever buying a box can use all of it. That is
the right posture for this work and it should stay true deliberately: the mesh tooling is not the moat, and
keeping it usable by people who never become customers is what makes it trustworthy to the ones who do.

## Three destinations, and only one of them has a deadline

"Getting your Brilliant onto your own network" is three different operations. They are worth naming separately
because their costs, their risks and their *availability over time* are nothing alike.

| | **A — Join their network** | **B — Migrate off it** | **C — Take over the glass** |
|---|---|---|---|
| What happens | Capture the panel's keys; a bridge joins the existing mesh and speaks it | Factory reset each switch; re-provision onto the owner's own mesh | Root the panel, our launcher becomes HOME |
| The panel | Stays exactly as it is, still working | Loses the switches; keeps its own loads | Keeps running underneath; new face |
| Reversible | Yes — nothing on the switches is touched | Not cheaply. Each switch is walked to and reset | Yes, in principle |
| Cost to the owner | None. No reset, no ladder, no downtime | Walking to every switch, plus re-doing load types, dimmer setup and multi-way pairings | One toggle, then the hub does it |
| Proven here | Yes — keys captured, bridge reading the live mesh | Yes — the stairway pair runs this way | **No.** Nothing written |
| **Still available after the cloud dies** | **No** | **Yes, forever** | Unknown — depends on whether root survives |

A and B are alternatives per switch — a mesh node belongs to one network at a time. C is orthogonal and composes
with either.

### The deadline, which is the part worth acting on

Path A looks strictly better than B on every row until the last one, and the last one decides it.

Capturing the panel's netkey works by **being provisioned by the panel** (`docs/brilliant.md`, *The live panel,
and capturing the netkey*): an ESP32 wears a real switch's QR identity and the panel provisions it, handing over
the key. That provisioning is driven from the **Brilliant mobile app's "Add a device" flow, and the app reaches
the panel through Brilliant's cloud.**

So the least invasive path depends on a server somebody else is paying for. The day that cloud goes dark, the
gentle option goes with it — not degraded, *gone* — and everyone who has not captured their keys is left with
path B and a screwdriver. Nothing announces this in advance, and the people most likely to miss it are exactly
the migrating owners above, whose system is working fine and who therefore have no reason to hurry.

**The consequence for the product is a sentence, not a feature: capture the keys while the cloud is up.** If an
owner does nothing else — does not migrate, does not take over the panel, does not buy anything — a captured
netkey sitting in a file is a door that stays open after the company is gone. That is the cheapest, most
time-sensitive advice this whole document contains, and it should probably be the first thing anyone is told.

*Unverified, and check 5 below: whether that Add-a-device flow needs the cloud at all, or only the app. If it
turns out to work on the LAN alone, the deadline moves from "when the servers stop" to "when the app stops
installing", which is later but no less certain.*

## Not a custom Android. A takeover kit.

The instinct is a custom ROM. It is the wrong shape, for three reasons that do not depend on the device:

- **The payoff is near zero.** The panel comes from the hub (`kiosk/README.md`). Our UI is a web app the brain
  serves, so an operating system we control buys no capability we do not already have on somebody else's.
- **The cost is board bringup, not a build.** Unknown SoC, unknown bootloader state, and drivers needed for the
  display, touch, radios, sensors and the mains board underneath. Months per device family, forever.
- **The screen is the part that fails.** Two panels here died the same way, blank and unrecoverable. A perfect
  OS on a dead display is nothing. Software cannot be the answer to a hardware failure.

What replaces it is three pieces, none of them new:

| Piece | What it is | State |
|---|---|---|
| **Root** | A way into the device's own Android | Per device. For Brilliant, official — see below |
| **The launcher** | `kiosk/` — `MAIN` + `HOME`, device owner, no way out but the corner | **Built.** Serves every device family, because it draws nothing of its own |
| **The resident bridge** | A small process left on the panel, speaking to the hub over MQTT | Not built. The only genuinely new work |

One launcher for all of them is the whole economy of this plan, and it holds only as long as `docs/apps.md`'s
rule holds: **there is never a second client.** A device that needs its own panel drawn for it is a device we
should decline rather than accommodate.

### Brilliant ships the door

Root SSH on a Brilliant Control is an **official, documented feature of the product**. Brilliant's own support
article describes enabling it and the permanent *"we can no longer certify this Control's software"* flag it
leaves on the Device Settings screen:
<https://support.brilliant.tech/hc/en-us/articles/21213665069851-Security-Status-on-Device-Settings>

No exploit, no bootloader unlock, no warranty argument — a toggle the owner flips on hardware they own. For the
device family that matters most, the hardest step of the kit is already solved by the manufacturer.

## The four layers, and which one is actually hard

The difficulty is inverted from how it looks.

| Layer | Difficulty | Why |
|---|---|---|
| **The glass** | Easy, and built | Root, install the APK, `cmd package set-home-activity`. The panel arrives from the hub |
| **The loads** | **Hard — and the first thing to prove** | A Brilliant Control *replaces a gang of switches*. If their service stops driving the triac when it is no longer the home screen, we have darkened somebody's hallway |
| **The radios** | Medium, and a gift | The panel firmware already translates its internal bus to the mesh |
| **Sensors** (PIR, camera, mic) | Bonus | Nothing here is required for the rescue to be worth doing |

**The loads row is the product rule.** Everything else on this page is optional; this is not. A rescue that
takes a working light switch and makes it a screen with a dead lamp under it is worse than leaving the house
alone, and an owner will judge it in the first ten seconds. *Prove the loads still work before writing anything
else for a new device.*

**The radios row is the one worth reading twice.** `docs/brilliant.md` (*Hunting the DFU trigger*) records that
`brilliant-mqtt` talks to the panel's **internal** message bus — a virtual `ble_mesh` device — and the panel's
own closed software translates that to mesh. This repo treated that as bad news, because it meant the raw vendor
opcodes live in firmware two dead panels would not give us. On a **live** panel it is the opposite: the firmware
does the translation for free. Keys, vendor fields, load-type writes, the DFU trigger that was declared not worth
brute-forcing — an owner's working panel is holding all of it. We took the difficult route because it was the
only one this house had.

## Per device

### Brilliant Control — the strong case

Official root, an Android of unknown but probably recent-enough vintage, and a mesh whose protocol this repo has
already mapped in detail. If any of these is a product, it is this one.

Two things an owner must be told before they touch anything:

- **The panel may be a switch position in a multi-way circuit.** `docs/brilliant.md` (*The house has three
  multi-way lights*) found the panel is an **end** of two of them — a slider on the glass is genuinely the third
  position of the kitchen three-way. Taking the panel off the wall costs that position. Taking over its software
  should not, but that is a thing to verify, not assume.
- **There is a fallback that already works.** If the takeover fails on a given panel, `brilliant/esp32-bridge`
  rescues the *switches* with no panel in the path at all — factory reset, re-provision, done. The panel is the
  better outcome; the switches are the floor, and the floor is built and running in this house.

### Wink Relay — rescue the hardware, not the glass

The Relay runs **Android 4.3**. Chromium WebView did not arrive until 4.4, so its WebView is a 2013 pre-Chromium
engine, and `kiosk/` declares `minSdk = 23` against the Relay's API 18. Our Vue panel will not run on that glass,
and lowering `minSdk` does not change the engine.

So the honest tier for the Relay is: **its hardware is worth rescuing; its screen probably is not.** Two load
relays, temperature, humidity and proximity, published over MQTT, make it a real device in an Elyir house,
controlled from phones and from walls that can render. Writing a stripped ES5 panel purely for it would break the
one-client rule above, and a 2013 device does not earn that.

Two caveats, both honest: **no Relay has been tested here** — this is from community reports, not a unit in hand,
and the API level should be confirmed on real hardware before the device is written off. And the community root
path runs **KingRoot**, a binary of uncertain provenance; whatever we ever recommend to a stranger, it cannot be
that.

### Commodity panels — the answer to "should we build hardware"

Rootable Android wall panels are sold new today, with published root tools and sideload guides (the Sonoff
NSPanel Pro is the worked example). That replaces "build a custom image" with **a supported-device list**, which
is a document rather than a product line, and it means the takeover kit has a future beyond rescuing the dead.

## The moment this has to be, to be a product

Rooting a wall panel is not an Apple-simple act, and the out-of-the-box promise does not bend for this. But
on Brilliant it can be, because the owner's only manual step is a toggle the manufacturer documents. Everything
after it is LAN work the hub can do itself:

> **We found a Brilliant Control in the hallway. Take it over?**

The hub connects, installs the launcher, leaves the bridge, sets the home activity. One toggle by a person, and
the rest is the box doing its job. If the kit ever needs a terminal in a customer's hands, it is not shipping.

## Rules

- **Never redistribute a vendor's binaries.** We ship our launcher and our bridge. Their firmware, their APKs and
  their keys stay on their device, where the owner already has a license to them.
- **Loads first, on every device.** See above. A dark room is a failed rescue however good the screen looks.
- **One launcher, no second client.** `docs/apps.md`. A device that needs its own UI is a device we decline.
- **Decide the posture deliberately.** Wink is abandoned; rescuing it is repair and nobody objects. Brilliant is
  alive and selling a subscription, and "keep your hardware when the company dies" is a different story from
  "stop paying the company that is still here." The *act* needs no defending — wanting the lamp in your hallway
  to work without somebody's servers is an ordinary preference, and it is most of why Home Assistant exists. It
  is the **framing** that needs care: lead with local control, which is true and durable, not with escaping a
  subscription, which reads as aimed at a company that is still trading. Worth a lawyer's read before either is
  printed on anything.

## What to check, in order

1. **Does the Brilliant app still expose Root SSH for a panel with a dead screen?** Cheapest check we have, and
   it now decides more than it used to: it is how this house gets a test rig for everybody else's panel.
2. **On any live Control: `getprop` the Android version and the installed WebView version.** One command once
   inside, and it decides whether our panel can run on Brilliant glass at all.
3. **Does the panel keep driving its own loads when it is not the home screen?** The rescue is worthless — worse
   than worthless — if the answer is no. Test before any bridge is written.
4. **Confirm a real Wink Relay's API level** before the tier above is treated as settled.
5. **Does the app's "Add a device" flow work with the phone on the LAN and no internet?** This decides whether
   the key-capture deadline above is "when Brilliant's servers stop" or something later, and it is the difference
   between advice that is merely good and advice that is urgent. Test by taking the phone off cellular and
   blocking the hub's WAN, then trying to add the spoof.

## What exists today

- `kiosk/` — the launcher. Built, running, device-owner capable. Needs no change to serve this plan.
- `brilliant/esp32-bridge` — the no-panel fallback for Brilliant switches. Built and running here.
- The resident bridge, the root recipes, and the hub-side "take it over?" flow — **none of it written.**
