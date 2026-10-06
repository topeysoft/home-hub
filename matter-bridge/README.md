# matter-bridge

The house, published as one Matter bridge, so Apple Home, Google Home and Alexa can see it. The plan
and the decisions behind it are `docs/matter.md`; this file is how to run it.

It is deliberately thin. It asks the brain for a list, builds one bridged endpoint per thing on it,
posts a command back when a commissioner sends one, and says what it is. **It decides nothing about
what may be shared** — that is `brain/hub/share.py`, where the rules have tests, because a rule in a
container with no tests is a rule nobody can check.

## Running it by hand

    npm install
    npm run build
    HUB_URL=http://localhost:8300 \
    HUB_SHARE_TOKEN=<the key from driver-layer/.env> \
    HUB_MATTER_PORT=5540 HUB_MATTER_STORAGE=./data \
    node dist/main.js

`npm run check` typechecks without emitting.

**Our variables are `HUB_*` and that is not a style choice.** matter.js reads the whole `MATTER_*`
namespace as its own configuration, so a `MATTER_STORAGE` of ours arrives as its `storage` and the
node refuses to start with *segment storage is not a map*. Anything added here stays out of its way.

## What it needs of the host

Host networking, for the same reason `matter-server` has it: commissioning needs mDNS and IPv6 on the
real LAN. Port 5540 by default — `matter-server` is a controller and does not listen there, so the two
do not collide.

`/data` holds the fabric credentials and the endpoint number each controller remembers a device by.
**Losing it is every ecosystem in the house starting again**, so it is a volume and it rides the backup.

## The three things this code is careful about

Each is a way bridges go wrong, and each has a comment at the point it matters:

- **The endpoint number.** Made in `share.py` from the device id and never from a name or a room, so
  renaming a lamp does not hand Apple Home a second lamp.
- **The echo.** Pushing the hub's state into an endpoint fires the same event a commissioner's command
  does. They are told apart by the value, which is the only way with no race in it.
- **Nothing running until somebody says so.** An empty list is no bridge at all — not an empty one.
  The container is silent until the panel's switch is thrown.

## What it publishes today

Lights (dimmable where the thing can dim) and plugs. Covers, the thermostat, fans and sensors are
piece 2. Locks are behind a switch of their own, alarms are never shared, and speakers, cameras and
scenes have nowhere in Matter to go — `docs/matter.md` says why for each.

## Ids

Vendor `0xfff1`, product `0x8001` — test ids, reserved for exactly this, and **not usable in a product
that is sold**. Apple Home commissions them; Google wants the pair registered in its developer console
first and a Google hub in the house; Alexa does not take an uncertified bridge at all today. The
shipping path is a CSA-issued vendor id and a certified model: `docs/matter.md`, *Certification*.
