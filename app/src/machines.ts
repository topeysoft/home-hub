/*
 * A machine, and the features it has.
 *
 * A fridge reaches the hub as four switches -- its ice maker, its Ice Bites, its power cool, its
 * power freeze -- each a device of its own, each a tile of its own, each named after the fridge.
 * That is a row of four plugs, and it is not what is standing in the kitchen. What is standing there
 * is one machine, and this file says which devices are one machine so the room can draw it as one.
 *
 * The rule is the hardware's, not the name's: the driver already says which entities belong to which
 * unit (`hw`), and the brain passes on what the unit is called (`hw_name`). Two or more appliance
 * features on one unit are a machine. One on its own stays a tile -- a dishwasher with a single
 * delay-start switch is a tile that says Dishwasher, and a card of one row would say less.
 *
 * Generic on purpose. A dishwasher, a washer, a dryer and an oven all arrive the same way, and a card
 * that knew what a fridge was would be a card that did not know what a dryer was. docs/kinds.md.
 */
import type { Device, Room } from './api'
import { cap, deviceById, shortName } from './store'

export type Machine = { key: string; name: string; devices: Device[] }

/** The machines among a room's devices, in the order their first feature appears, and the devices
    left over that are not part of one. A device is a feature of a machine when it is shown as an
    appliance and shares its unit with at least one other. */
export function machinesOf(devices: Device[]): { machines: Machine[]; rest: Device[] } {
  const byUnit = new Map<string, Device[]>()
  for (const d of devices) if (cap(d) === 'appliance' && d.hw) byUnit.set(d.hw, [...(byUnit.get(d.hw) ?? []), d])
  const machines: Machine[] = []
  const grouped = new Set<string>()
  for (const [hw, ds] of byUnit) {
    if (ds.length < 2) continue
    machines.push({ key: `machine:${hw}`, name: machineName(ds), devices: ds })
    for (const d of ds) grouped.add(d.id)
  }
  return { machines, rest: devices.filter(d => !grouped.has(d.id)) }
}

/** What the machine is called: what the driver calls the unit, else the words its features share
    ("Refrigerator Ice Maker" and "Refrigerator Ice Bites" share "Refrigerator"), else "Appliance". */
export function machineName(devices: Device[]): string {
  const unit = devices.find(d => d.hw_name)?.hw_name?.trim()
  if (unit) return unit
  const words = devices.map(d => d.name.trim().split(/\s+/))
  const shared: string[] = []
  for (let i = 0; i < Math.min(...words.map(w => w.length)); i++) {
    if (words.every(w => w[i].toLowerCase() === words[0][i].toLowerCase())) shared.push(words[0][i]); else break
  }
  return shared.join(' ') || 'Appliance'
}

/** A feature's own name on its machine's card: "Refrigerator Ice Maker" under "Refrigerator" is
    "Ice Maker". A name that is nothing but the machine's is left whole rather than blank. */
export function featureName(d: Device, machine: string, room?: Room | null): string {
  const n = shortName(d, room), m = machine.trim().toLowerCase()
  if (m && n.toLowerCase().startsWith(m + ' ')) {
    const rest = n.slice(m.length + 1).trim()
    if (rest) return rest.charAt(0).toUpperCase() + rest.slice(1)
  }
  return n
}

/* ---------- the machine, opened ----------
   Holding the card opens the machine, the way holding any tile opens the thing on it. A machine is not a
   device the brain knows, so the pane is handed one made here: named after the machine, in its room, on
   its hardware, with its features under `attrs.parts`. Everything the pane says about it is read off
   the features live (partsOfMachine), so the sheet stays true while somebody taps rows on it. Renaming
   or moving it goes through its first feature, which the brain moves and renames as the hardware. */
export const isMachine = (d: Device) => d.capability === 'machine'
export function asDevice(m: Machine): Device {
  const first = m.devices[0]
  return { id: m.key, name: m.name, room_id: first.room_id, capability: 'machine', state: m.devices.some(d => d.state === 'on') ? 'on' : 'off',
           attrs: { parts: m.devices.map(d => d.id) }, hw: first.hw, hw_name: m.name, maker: first.maker ?? null }
}
/** The machine's features, looked up fresh, so a row that was just tapped reads as it now is. */
export const partsOfMachine = (d: Device): Device[] => ((d.attrs.parts as string[] | undefined) ?? []).map(id => deviceById(id)).filter((x): x is Device => !!x)
