# Units: a switch with a motion sensor built in

*Written 16 September 2026, from "a lot of switches have an integrated motion sensor -- the Brilliant wall switch,
and others -- and mine are detected separately from their sensor, both asking me for a room. I should not have to
guess which sensor goes with which switch."*

## What the house already knew

A Brilliant Smart Dimmer, a Ring pathlight, a GE motion switch: one thing on the wall that reaches Home Assistant
as two entities, a `light` and a `binary_sensor` of class motion, on one device in HA's registry. The brain has
kept that device id on every `Device` as `hw` since rooms were first movable, and `POST /devices/{id}/move` moves
the hardware, so moving either part always moved the unit. The registry on the hub that asked confirms the shape:
every Ring *Lighting Switch/Light*, every Ring *Lighting Group* and the Brilliant switch on the ESP32 bridge is a
light and a motion sensor on one unit.

So nothing was wrong in the brain. The panel met the parts separately in two places, and both are fixed here.

## New devices: one row per unit

`app/src/units.ts` `unitsOf()` groups a room's devices by `hw` where the hardware has two or more parts, and
`SortView.vue` draws a row per unit rather than per device: the unit's name (what the driver calls the hardware,
`Device.hw_name`), and under it the parts in a word each -- *Light · Motion* -- so nobody has to guess which sensor
is which switch's. One room picker; picking moves the lead part, and the brain moves the hardware as it always did.
The brain's own room proposal is read off the lead part; `suggest.py` already looked at a unit's siblings when it
proposed, so the proposal was the unit's before the row was.

**Renaming the unit is a new route shape.** `POST /devices/{id}/rename` with `{"name": ..., "unit": true}` renames
the hardware (`device_registry/update name_by_user`) and carries its parts along. Two kinds of part: one HA names
after the unit (`has_entity_name`, kept as `Device.named_by_unit`) and renames for free, and it must NOT be given a
name of its own or it becomes "Garage Left Light Garage Left Light Motion"; the other carries its own name and
follows only where that name began with the unit's, so a sensor somebody already called "Steps" keeps it.
`Hub.rename_unit()` in `api.py`; the panel does the same follow-along in `renameParts()` so the rows read right
before the rebuild confirms it.

## The room: the sensor is on the switch's tile

`Home.build()` hands a light, switch or fan the motion sensor on its hardware as `attrs["motion"]`, the same move
as a floodlight camera being handed its lamp (`Home.lamps`; this is `Home.eyes`), and kept through state changes
by `attrs_for()`. On the panel:

- The tile's one line says *On · Motion* while the sensor sees someone (`LightTile.vue`, `PlainTile.vue`, through
  `seeing()`), and the pane lists *Motion sensor: Seeing motion / Nobody about* among its facts.
- The reading strip leaves out a sensor whose switch is a tile in the same room (`onATile()`): the switch is
  where the thing is, and a chip saying Motion beside a tile saying Motion is the same fact twice. A sensor whose
  switch is in another room, or on no tile, stays on the strip as before.
- A part named "unit + kind" the way HA composes them -- "Walkway Pathlight Light" -- is called by the unit's name
  on its tile (`shortName()`), then the room's name comes off as ever.

The sensor stays a device of its own throughout. Rules (`when: {motion: true}`), the room's line ("Motion"), and
the Rooms tab read it as they always did.

## Renaming, and where it was missing

*Same day: "there doesn't seem to be any way to change the name of a device."* There were two, and neither
could be found. The pane's *Rename or move it* verb opened the house's settings panel, which has no rename in it
-- a promise the button made and the panel broke. And the room's edit view (the pencil by the room's name) had
name fields styled as plain text until touched, which on a wall with no cursor is plain text.

Now the verb does what it says, on the pane: the room line and the name turn into a room picker and a name field,
Done saves both, Cancel or Escape puts them back (`Opened.vue`, `startEdit()` / `saveEdit()`). What it renames is
what you see: a thing whose name IS its unit's ("Walkway Pathlight Light" on hardware called "Walkway Pathlight")
renames the unit, and the field is filled with the unit's name and says so under it; a fridge's "Ice Maker" is a
feature and renames only itself (`renamesUnit()` in units.ts). The edit rows look like fields (`.sort-name`), and
in a room's edit view a unit -- or a machine, which shares the hardware grouping -- is one row named after the unit,
its parts under it; a single part is renamed from its own pane.

## Kept apart from machines on purpose

`machines.ts` groups by the same field for a different reason. A fridge's features are all of a kind and want one
card; a switch and its sensor are a thing and what it senses, and want one tile with one word on it. The two files
say so in their headers so that nobody merges them.

## Tests

`brain/tests/test_api_house.py` `UnitTests` (the attachment, its survival of a state change, the two kinds of part
under a rename, and the plain rename left alone) and `app/tests/units.test.ts` (the rows, the words, the follow-along,
seeing, the strip, and the names).
