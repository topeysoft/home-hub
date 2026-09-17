/*
 * A unit, and the parts it has.
 *
 * A Brilliant dimmer, a Ring pathlight, a motion switch: one thing on the wall that reaches the hub
 * as two devices, a light and a motion sensor, on one piece of hardware. The brain already treats
 * the hardware as the thing -- moving either part moves the unit -- and this file is the panel's
 * side of the same fact, in the two places a person meets the parts separately:
 *
 *   New devices, where a unit used to be two rows asking for a room twice, and nothing on the screen
 *   said which motion sensor was which switch's. Here it is one row, its parts named under it.
 *
 *   The room, where the switch's own motion sensor is a chip on the reading strip while the switch is
 *   a tile. The brain hands the tile its sensor (`attrs.motion`, the way a floodlight camera is handed
 *   its lamp), so the tile says Motion and the strip does not say it twice.
 *
 * machines.ts groups by the same field for a different reason -- a fridge's features are all of a
 * kind, and want one card -- and the two are kept apart on purpose: a unit is a thing and its sensor,
 * a machine is a thing and its features.
 */
import type { Device, Room } from './api'
import { cap, deviceById, shortName, store, unitNamed } from './store'
import { isReading } from './readings'

/** One row of New devices: a device on its own, or a unit with its parts. `lead` is the device the
    row acts through -- its rename, move and suggestion are the unit's -- and it is the part a person
    would name the unit after: what it controls before what it senses. */
export type UnitRow = { key: string; name: string; lead: Device; parts: Device[] }

export function unitsOf(devices: Device[]): UnitRow[] {
  const byHw = new Map<string, Device[]>()
  for (const d of devices) if (d.hw) byHw.set(d.hw, [...(byHw.get(d.hw) ?? []), d])
  const rows: UnitRow[] = [], done = new Set<string>()
  for (const d of devices) {
    if (done.has(d.id)) continue
    const parts = d.hw ? byHw.get(d.hw) ?? [d] : [d]
    if (parts.length < 2) { rows.push({ key: d.id, name: d.name, lead: d, parts: [d] }); continue }
    const lead = parts.find(p => !isReading(p)) ?? parts[0]
    rows.push({ key: `unit:${d.hw}`, name: unitName(parts), lead, parts })
    for (const p of parts) done.add(p.id)
  }
  return rows
}

/** What a unit is called: what the driver calls the hardware, else what its lead part is called. */
export function unitName(parts: Device[]): string {
  const unit = parts.find(p => p.hw_name)?.hw_name?.trim()
  if (unit) return unit
  return (parts.find(p => !isReading(p)) ?? parts[0]).name
}

/** The word for a part under its unit's name: "Light · Motion". The part's own name where it is
    not simply the unit's name plus its kind -- a sensor somebody called "Steps" is "Steps". */
export function partWord(d: Device, unit: string): string {
  const words: Record<string, string> = { light: 'Light', switch: 'Switch', fan: 'Fan', motion: 'Motion', contact: 'Door sensor', media: 'Speaker',
    cover: 'Blind', lock: 'Lock', climate: 'Thermostat', camera: 'Camera', vacuum: 'Vacuum', alarm: 'Alarm', appliance: 'Appliance' }
  const k = cap(d), kind = k === 'sensor' ? ({ temperature: 'Temperature', humidity: 'Humidity', illuminance: 'Light level' } as Record<string, string>)[d.capability.split('.')[1]] ?? 'Reading' : words[k] ?? k
  const n = d.name.trim(), u = unit.trim().toLowerCase()
  if (!n || n.toLowerCase() === u) return kind
  const rest = n.toLowerCase().startsWith(u + ' ') ? n.slice(u.length + 1).trim() : n
  return new RegExp(`^(${kind}|${k}|sensor|detector)$`, 'i').test(rest) ? kind : rest.charAt(0).toUpperCase() + rest.slice(1)
}

/** After a unit is renamed on the panel: the same follow-along the brain does, so the rows read right
    before the house confirms it. Parts HA names after the unit are left to HA. */
export function renameParts(parts: Device[], was: string, name: string) {
  for (const p of parts) {
    p.hw_name = name
    if (p.named_by_unit || !was) continue
    const n = p.name.trim()
    if (n.toLowerCase() === was.toLowerCase()) p.name = name
    else if (n.toLowerCase().startsWith(was.toLowerCase() + ' ')) p.name = `${name} ${n.slice(was.length + 1)}`
  }
}

/** The motion sensor built into this thing, when the brain has said there is one and it is in view. */
export const eyeOf = (d: Device): Device | undefined => d.attrs.motion ? deviceById(String(d.attrs.motion)) : undefined
/** Seeing motion right now, through its own sensor. */
export const seeing = (d: Device) => eyeOf(d)?.state === 'on'
/** A motion sensor that is on a tile in this room already, and so has no chip of its own on the strip. */
export function onATile(sensor: Device, room: Room): boolean {
  return cap(sensor) === 'motion' && room.devices.some(d => d.attrs.motion === sensor.id && !isReading(d))
}
/** Said on the strip for the sensors that stay there: their own name, with the unit's in front taken off. */
export const sensorName = (d: Device, room?: Room | null) => d.hw_name && shortName(d, room).toLowerCase().startsWith(d.hw_name.toLowerCase() + ' ') ? shortName(d, room).slice(d.hw_name.length + 1) : shortName(d, room)

/** Every device on the same hardware as this one, across the house, itself included. */
export const partsOf = (d: Device): Device[] => d.hw ? store.rooms.flatMap(r => r.devices.filter(x => x.hw === d.hw)) : [d]
/** Renaming this thing from its own pane means renaming the unit when the thing IS the unit -- a light
    called "Walkway Pathlight Light" on hardware called "Walkway Pathlight" -- and only the thing otherwise:
    a fridge's "Ice Maker" is a feature, and renaming it must not rename the fridge. */
export const renamesUnit = (d: Device) => unitNamed(d) && partsOf(d).length > 1

/* ---------- a fan with a light in it ----------
   One fixture on the ceiling, two devices to the driver. The brain tells each part the other (`attrs.light`
   on the fan, `attrs.fan` on the light) and both which of them is the tile (`attrs.leads`): the fan unless
   the owner says the light, from either part's pane. The other part is CARRIED -- a row on the lead's
   tile, tap to switch, hold to open -- and has no tile of its own while its lead is in the room. It is
   still a device: scenes, "lights off" and the room's line reach it as ever. */

/** The other half of this thing's fixture, when it has one and it is in view. */
export function partnerOf(d: Device): Device | undefined {
  const k = cap(d)
  const id = k === 'fan' ? d.attrs.light : k === 'light' ? d.attrs.fan : null
  return id ? deviceById(String(id)) : undefined
}
/** This thing is the tile of its fixture. */
export const leadsFixture = (d: Device) => !!partnerOf(d) && d.attrs.leads === cap(d)
/** This thing rides on its partner's tile in this room, and so draws none of its own. */
export const isCarried = (d: Device, room: Room) => {
  const p = partnerOf(d)
  return !!p && d.attrs.leads !== cap(d) && room.devices.some(x => x.id === p.id)
}
/** A fan's speed in a word: the three the pane offers, or On where it does not say. */
export function speedWord(d: Device): string {
  if (d.state !== 'on') return 'Off'
  const pct = Number(d.attrs.percentage)
  if (!Number.isFinite(pct) || !pct) return 'On'
  return pct <= 40 ? 'Low' : pct <= 75 ? 'Medium' : 'High'
}
