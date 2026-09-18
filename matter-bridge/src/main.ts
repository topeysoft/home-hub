// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The house, published as one Matter bridge: docs/matter.md, piece 1.
 *
 * An Aggregator with one bridged endpoint per shared thing, on the test vendor id, announcing itself
 * on the LAN. Apple Home commissions it today; Google wants the id pair registered first and a hub in
 * the house; Alexa does not yet take an uncertified bridge at all. None of that is decided here, and
 * nor is WHAT may be shared -- that is `brain/hub/share.py`, where the rules have tests.
 *
 * Three things this file is careful about, each of which is a way bridges go wrong:
 *
 *   - THE ENDPOINT NUMBER. A commissioner remembers a thing by its endpoint number, and matter.js
 *     remembers the number against the id we hand it. That id is made in `share.py` from the device
 *     id and never from its name or its room, so renaming a lamp does not hand Apple Home a new lamp.
 *   - THE ECHO. Pushing the hub's state into an endpoint fires the same change event a commissioner's
 *     command does. Telling them apart by the VALUE rather than by a flag is the one way with no race
 *     in it: a command that agrees with what we last pushed changed nothing, and so was not a command.
 *   - NOTHING RUNNING UNTIL SOMEBODY SAYS SO. An empty list is not an empty bridge; it is no bridge
 *     at all. A house that never opened the screen announces nothing to the network.
 */
import { Endpoint, Environment, ServerNode, StorageService, VendorId } from "@matter/main";
import { BridgedDeviceBasicInformationServer } from "@matter/main/behaviors/bridged-device-basic-information";
import { DoorLockServer } from "@matter/main/behaviors/door-lock";
import { OccupancySensingServer } from "@matter/main/behaviors/occupancy-sensing";
import { ThermostatServer } from "@matter/main/behaviors/thermostat";
import { MovementDirection, WindowCoveringServer } from "@matter/main/behaviors/window-covering";
import { ContactSensorDevice } from "@matter/main/devices/contact-sensor";
import { DimmableLightDevice } from "@matter/main/devices/dimmable-light";
import { DoorLockDevice } from "@matter/main/devices/door-lock";
import { FanDevice } from "@matter/main/devices/fan";
import { HumiditySensorDevice } from "@matter/main/devices/humidity-sensor";
import { OccupancySensorDevice } from "@matter/main/devices/occupancy-sensor";
import { OnOffLightDevice } from "@matter/main/devices/on-off-light";
import { OnOffPlugInUnitDevice } from "@matter/main/devices/on-off-plug-in-unit";
import { TemperatureSensorDevice } from "@matter/main/devices/temperature-sensor";
import { ThermostatDevice } from "@matter/main/devices/thermostat";
import { WindowCoveringDevice } from "@matter/main/devices/window-covering";
import { AggregatorEndpoint } from "@matter/main/endpoints/aggregator";
import { act, configured, report, shared, watch, type BridgeStatus, type SharedDevice } from "./hub.js";

// HUB_ rather than MATTER_, and it is not a style choice: matter.js reads the whole MATTER_* namespace
// as its own configuration, so a MATTER_STORAGE of ours lands as its `storage` and the node then fails
// to start with "segment storage is not a map". Our variables stay out of its namespace.
const PORT = Number(process.env.HUB_MATTER_PORT ?? 5540);
const STORAGE = process.env.HUB_MATTER_STORAGE ?? "/data";
// Test ids. 0xfff1-0xfff4 are reserved for exactly this and may not be used in a product that is
// sold; a real one is a CSA-issued vendor id and a certified model. docs/matter.md, *Certification*.
const VENDOR_ID = 0xfff1;
const PRODUCT_ID = 0x8001;
// What this bridge says it is running. A commissioner shows it, and an update that changes what the
// house publishes should be visible over there rather than only in our own release notes.
const VERSION = "0.1.0";
const SOFTWARE_VERSION = 1;

import {
    fromCenti, fromLift, MODE_FROM_MATTER, MODE_TO_MATTER, toCenti, toCentiPct, toLevel, toLift, toPercent,
} from "./units.js";

/**
 * One published thing. The endpoint itself is reached only through these closures, made in the branch
 * that knows what kind of endpoint it is -- so a `currentLevel` can never be pushed at a plug, and
 * nothing here has to be cast to make the compiler stop asking.
 */
interface Published {
    device: SharedDevice;
    /** What we last pushed in, by attribute, and therefore what an echo would look like. A change
     *  that agrees with what is here came from us and is not a command. */
    pushed: Record<string, unknown>;
    info(d: SharedDevice): Promise<void>;
    /** Apply the house's state to the endpoint, in whatever way this kind of endpoint needs. */
    push(d: SharedDevice): Promise<void>;
    close(): Promise<void>;
}

/** Endpoint id -> the thing it is, so a behavior handling a command can find its way back to the
 *  device it belongs to. A subclassed behavior has its endpoint and nothing else. */
const byEid = new Map<string, Published>();

/** A command from a commissioner, on its way to the brain. */
function command(eid: string | undefined, action: string, data?: Record<string, unknown>) {
    const entry = eid ? byEid.get(eid) : undefined;
    if (!entry) return;
    void act(entry.device.id, action, data);
}

/** Did this change come from us. Every command handler asks first, and the answer is the value we
 *  last pushed rather than a flag, which is the one way round with no race in it. */
function echo(entry: Published, key: string, value: unknown) {
    if (entry.pushed[key] === value) return true;
    entry.pushed[key] = value;
    return false;
}

/** A lock's two commands. matter.js has no attribute to watch here -- a controller invokes a command
 *  -- so this is the behavior, and the endpoint's id is the only thread back to the device. */
class HubLock extends DoorLockServer {
    override async lockDoor() { command(this.endpoint.id, "lock"); }
    override async unlockDoor() { command(this.endpoint.id, "unlock"); }
}

/** A cover's movement. `targetPercent100ths` is Matter's way round; `fromLift` puts it back into the
 *  house's. Where a controller just says open or close, say that instead -- a cover with no position
 *  of its own (a garage door) can do those and nothing else. */
class HubCover extends WindowCoveringServer.with("Lift", "PositionAwareLift") {
    override async handleMovement(_type: unknown, _reversed: boolean, direction: MovementDirection, targetPercent100ths?: number) {
        const eid = this.endpoint.id;
        if (targetPercent100ths !== undefined) return void command(eid, "set", { position: fromLift(targetPercent100ths) });
        command(eid, direction === MovementDirection.Close ? "close" : "open");
    }
}

const published = new Map<string, Published>();
/* Endpoints that would not build. Without this a single bad device is retried on every nudge and
   every heartbeat, and each attempt allocates a Matter endpoint number it then throws away -- so one
   thing the bridge cannot carry slowly eats the numbering the rest of the house depends on. */
const broken = new Set<string>();
let server: ServerNode | undefined;
let aggregator: Endpoint | undefined;
let working = false;
let again = false;

/** What a commissioner is told this thing is. The room rides along inside the label, because there is
 * no standard way to push a room assignment and both Apple and Google have ignored the label that
 * looks like one -- so a person assigns rooms once more over there. docs/matter.md says so out loud. */
function describe(d: SharedDevice) {
    return {
        nodeLabel: d.name.slice(0, 32),
        productName: d.name.slice(0, 32),
        productLabel: (d.room ? `${d.room} · ${d.name}` : d.name).slice(0, 64),
        serialNumber: d.eid,
        reachable: d.reachable,
    };
}

/**
 * One endpoint, built as the kind of thing it is. A branch each rather than one device type computed
 * on the fly, so the state each is handed is actually checked: a `currentLevel` on a plug, or a
 * setpoint on a contact sensor, should be a mistake the compiler catches here and not a cluster a
 * commissioner finds missing a week later.
 *
 * Each branch owns its own conversions into Matter's units, and returns the closure that applies the
 * house's state to it. Nothing outside knows what cluster anything is.
 */
async function add(d: SharedDevice) {
    const common = { id: d.eid, bridgedDeviceBasicInformation: describe(d) };
    const info = (e: { set(v: object): Promise<void> }) => async (next: SharedDevice) => { await e.set({ bridgedDeviceBasicInformation: describe(next) }); };
    let entry: Published;

    if (d.type === "light" && d.dim) {
        const e = new Endpoint(DimmableLightDevice.with(BridgedDeviceBasicInformationServer), {
            ...common, onOff: { onOff: !!d.state.on }, levelControl: { currentLevel: toLevel(d.state.brightness ?? null) },
        });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { on: !!d.state.on, level: toLevel(d.state.brightness ?? null) },
            info: info(e), close: () => e.close(),
            push: async next => {
                const level = toLevel(next.state.brightness ?? null);
                if (!echo(entry, "on", !!next.state.on)) await e.set({ onOff: { onOff: !!next.state.on } });
                if (!echo(entry, "level", level)) await e.set({ levelControl: { currentLevel: level } });
            },
        };
        e.events.levelControl.currentLevel$Changed.on(v => {
            if (v === null || echo(entry, "level", v)) return;
            entry.pushed.on = true;   // a level always arrives with the light meant to be on
            void act(entry.device.id, "on", { brightness_pct: toPercent(v) });
        });
        e.events.onOff.onOff$Changed.on(on => { if (!echo(entry, "on", on)) void act(entry.device.id, on ? "on" : "off"); });
    } else if (d.type === "light" || d.type === "plug") {
        const e = d.type === "light"
            ? new Endpoint(OnOffLightDevice.with(BridgedDeviceBasicInformationServer), { ...common, onOff: { onOff: !!d.state.on } })
            : new Endpoint(OnOffPlugInUnitDevice.with(BridgedDeviceBasicInformationServer), { ...common, onOff: { onOff: !!d.state.on } });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { on: !!d.state.on }, info: info(e), close: () => e.close(),
            push: async next => { if (!echo(entry, "on", !!next.state.on)) await e.set({ onOff: { onOff: !!next.state.on } }); },
        };
        e.events.onOff.onOff$Changed.on(on => { if (!echo(entry, "on", on)) void act(entry.device.id, on ? "on" : "off"); });
    } else if (d.type === "fan") {
        // `fanModeSequence` is mandatory and says which named speeds exist. Off/Low/Medium/High is the
        // one every controller understands; the house is driven by the percentage underneath it, and
        // `fanMode` is kept beside it so an app that only offers the three names still works.
        const speed = (p: number) => (p <= 0 ? 0 : p <= 33 ? 1 : p <= 66 ? 2 : 3);
        const pct = Math.round(d.state.on ? (d.state.percent ?? 100) : 0);
        const e = new Endpoint(FanDevice.with(BridgedDeviceBasicInformationServer), {
            ...common, fanControl: { fanModeSequence: 0, fanMode: speed(pct), percentSetting: pct, percentCurrent: pct },
        });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { pct }, info: info(e), close: () => e.close(),
            push: async next => {
                // A fan that is off is a fan at nought per cent as far as Matter is concerned: it has
                // no on of its own, and reporting a speed for a stopped fan is how it shows as running.
                const p = next.state.on ? Math.round(next.state.percent ?? 100) : 0;
                if (!echo(entry, "pct", p)) await e.set({ fanControl: { fanMode: speed(p), percentSetting: p, percentCurrent: p } });
            },
        };
        e.events.fanControl.percentSetting$Changed.on(v => {
            if (v === null || echo(entry, "pct", v)) return;
            if (v === 0) void act(entry.device.id, "off");
            else void act(entry.device.id, "set", { percentage: v });
        });
    } else if (d.type === "cover") {
        const lift = toLift(d.state.position);
        const e = new Endpoint(WindowCoveringDevice.with(HubCover, BridgedDeviceBasicInformationServer), {
            ...common, windowCovering: { currentPositionLiftPercent100ths: lift, targetPositionLiftPercent100ths: lift },
        });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { lift }, info: info(e), close: () => e.close(),
            push: async next => {
                const l = toLift(next.state.position);
                if (echo(entry, "lift", l)) return;
                await e.set({ windowCovering: { currentPositionLiftPercent100ths: l, targetPositionLiftPercent100ths: l } });
            },
        };
    } else if (d.type === "lock") {
        // A lock the driver is unsure of is `notFullyLocked` rather than a guess either way: Apple Home
        // then says it does not know, which is true, instead of showing a bolt that may not be thrown.
        const lockState = d.state.known === false ? 0 : d.state.locked ? 1 : 2;
        const e = new Endpoint(DoorLockDevice.with(HubLock, BridgedDeviceBasicInformationServer), {
            // Type and operating mode are mandatory. The house knows neither and does not need to: a
            // deadbolt in normal operation is what a bridged lock is, and `actuatorEnabled` says the
            // bolt can actually be driven, which is the whole reason it is here.
            ...common,
            // A THIRD INVERSION, and the specification itself warns about this one: in
            // `supportedOperatingModes` a bit that is SET means the mode is NOT supported. So normal
            // is false and everything else true, which reads backwards and is correct.
            doorLock: {
                lockState, lockType: 0, actuatorEnabled: true, operatingMode: 0,
                // Both of these belong to PIN codes this lock does not have, and both are validated
                // against a 1..255 range whose default is 0 -- so they have to be given values even
                // though nothing will ever read them. Three tries and ten seconds are the usual ones.
                wrongCodeEntryLimit: 3, userCodeTemporaryDisableTime: 10,
                // ...and the specification also says every bit it has not defined shall be 1, which
                // matter.js surfaces as `alwaysSet`. Leave it out and the lock refuses to build at all.
                supportedOperatingModes: {
                    normal: false, vacation: true, privacy: true, noRemoteLockUnlock: true, passage: true, alwaysSet: 0x7ff,
                },
                // The two code-entry attributes above are validated at runtime but are not in the type
                // unless PinCredential is enabled -- a feature this lock does not have and must not
                // claim to. So the literal is asserted, narrowly, and only here.
            } as never,
        });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { lockState }, info: info(e), close: () => e.close(),
            push: async next => {
                const st = next.state.known === false ? 0 : next.state.locked ? 1 : 2;
                if (!echo(entry, "lockState", st)) await e.set({ doorLock: { lockState: st } });
            },
        };
    } else if (d.type === "occupancy") {
        // Since revision 5 the cluster wants the detector type declared as a FEATURE, not only as an
        // attribute. Passive infrared is what nearly every motion sensor in a house is.
        const e = new Endpoint(OccupancySensorDevice.with(OccupancySensingServer.with("PassiveInfrared"), BridgedDeviceBasicInformationServer), {
            // The sensor TYPE is mandatory. The house does not know how a motion sensor senses and does
            // not need to; PIR is what nearly all of them are and what a controller expects to see.
            ...common,
            occupancySensing: { occupancy: { occupied: !!d.state.detected }, occupancySensorType: 0, occupancySensorTypeBitmap: { pir: true } },
        });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { seen: !!d.state.detected }, info: info(e), close: () => e.close(),
            push: async next => {
                if (!echo(entry, "seen", !!next.state.detected)) await e.set({ occupancySensing: { occupancy: { occupied: !!next.state.detected } } });
            },
        };
    } else if (d.type === "contact") {
        // THE OTHER INVERSION. A binary sensor is on when the door is OPEN; Matter's contact sensor
        // says the opposite -- false is open, true is contact made.
        const e = new Endpoint(ContactSensorDevice.with(BridgedDeviceBasicInformationServer), {
            ...common, booleanState: { stateValue: !d.state.open },
        });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { shut: !d.state.open }, info: info(e), close: () => e.close(),
            push: async next => {
                if (!echo(entry, "shut", !next.state.open)) await e.set({ booleanState: { stateValue: !next.state.open } });
            },
        };
    } else if (d.type === "temperature") {
        const measuredValue = toCenti(d.state.value, d.unit);
        const e = new Endpoint(TemperatureSensorDevice.with(BridgedDeviceBasicInformationServer), { ...common, temperatureMeasurement: { measuredValue } });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { measuredValue }, info: info(e), close: () => e.close(),
            push: async next => {
                const v = toCenti(next.state.value, next.unit);
                if (!echo(entry, "measuredValue", v)) await e.set({ temperatureMeasurement: { measuredValue: v } });
            },
        };
    } else if (d.type === "humidity") {
        const measuredValue = toCentiPct(d.state.value);
        const e = new Endpoint(HumiditySensorDevice.with(BridgedDeviceBasicInformationServer), { ...common, relativeHumidityMeasurement: { measuredValue } });
        await aggregator!.add(e);
        entry = {
            device: d, pushed: { measuredValue }, info: info(e), close: () => e.close(),
            push: async next => {
                const v = toCentiPct(next.state.value);
                if (!echo(entry, "measuredValue", v)) await e.set({ relativeHumidityMeasurement: { measuredValue: v } });
            },
        };
    } else {
        // A thermostat, built to what this one can actually do. `controlSequenceOfOperation` is
        // mandatory and has to agree with the features: claiming Cooling on a heat-only system puts a
        // cooling dial in Apple Home for something that cannot cool. The house's own `modes` decide.
        const unit = d.unit;
        const modes = d.state.modes ?? [];
        const canHeat = modes.includes("heat") || modes.includes("heat_cool") || modes.length === 0;
        const canCool = modes.includes("cool") || modes.includes("heat_cool") || modes.length === 0;
        const heat = toCenti(d.state.target_low ?? d.state.target, unit) ?? 2000;
        const cool = toCenti(d.state.target_high ?? d.state.target, unit) ?? 2400;
        const mode = MODE_TO_MATTER[d.state.mode ?? "off"] ?? 0;
        const local = toCenti(d.state.current, unit);
        const base = { ...common, thermostat: { localTemperature: local, systemMode: mode } };

        /* Three shapes of thermostat, and the state each is handed differs -- a heat-only server has
           no cooling setpoint to write. Construction stays fully typed; only the pushing closure
           below is structural, because writing it three times is three places to fix a bug once. */
        type Thermo = {
            set(v: { thermostat: Record<string, unknown> }): Promise<void>;
            close(): Promise<void>;
            events: { thermostat: Record<string, { on(cb: (v: number | null) => void): unknown }> };
        };
        let e: Thermo;
        if (canHeat && canCool) {
            e = new Endpoint(ThermostatDevice.with(ThermostatServer.with("Heating", "Cooling"), BridgedDeviceBasicInformationServer), {
                ...base, thermostat: { ...base.thermostat, controlSequenceOfOperation: 4, occupiedHeatingSetpoint: heat, occupiedCoolingSetpoint: cool },
            }) as unknown as Thermo;
        } else if (canHeat) {
            e = new Endpoint(ThermostatDevice.with(ThermostatServer.with("Heating"), BridgedDeviceBasicInformationServer), {
                ...base, thermostat: { ...base.thermostat, controlSequenceOfOperation: 2, occupiedHeatingSetpoint: heat },
            }) as unknown as Thermo;
        } else {
            e = new Endpoint(ThermostatDevice.with(ThermostatServer.with("Cooling"), BridgedDeviceBasicInformationServer), {
                ...base, thermostat: { ...base.thermostat, controlSequenceOfOperation: 0, occupiedCoolingSetpoint: cool },
            }) as unknown as Thermo;
        }
        await aggregator!.add(e as unknown as Endpoint);

        entry = {
            device: d, pushed: { heat, cool, mode, local },
            info: async next => { await (e as unknown as { set(v: object): Promise<void> }).set({ bridgedDeviceBasicInformation: describe(next) }); },
            close: () => e.close(),
            push: async next => {
                const u = next.unit;
                const h = toCenti(next.state.target_low ?? next.state.target, u);
                const c = toCenti(next.state.target_high ?? next.state.target, u);
                const l = toCenti(next.state.current, u);
                const m = MODE_TO_MATTER[next.state.mode ?? "off"] ?? 0;
                if (l !== null && !echo(entry, "local", l)) await e.set({ thermostat: { localTemperature: l } });
                if (canHeat && h !== null && !echo(entry, "heat", h)) await e.set({ thermostat: { occupiedHeatingSetpoint: h } });
                if (canCool && c !== null && !echo(entry, "cool", c)) await e.set({ thermostat: { occupiedCoolingSetpoint: c } });
                if (!echo(entry, "mode", m)) await e.set({ thermostat: { systemMode: m } });
            },
        };

        // A setpoint dragged in the other app. `climate.set_temperature` takes one number, so the one
        // that moved is the one that is sent -- which is what somebody dragging a dial meant.
        const onAttr = (name: string, run: (v: number) => void) =>
            e.events.thermostat[name]?.on(v => { if (v !== null && !echo(entry, name === "systemMode" ? "mode" : name === "occupiedHeatingSetpoint" ? "heat" : "cool", v)) run(v); });
        onAttr("occupiedHeatingSetpoint", v => void act(entry.device.id, "set", { temperature: fromCenti(v, entry.device.unit) }));
        onAttr("occupiedCoolingSetpoint", v => void act(entry.device.id, "set", { temperature: fromCenti(v, entry.device.unit) }));
        onAttr("systemMode", v => { const hv = MODE_FROM_MATTER[v]; if (hv) void act(entry.device.id, "mode", { hvac_mode: hv }); });
    }

    byEid.set(d.eid, entry);
    published.set(d.id, entry);
    console.log(`published ${d.name} (${d.room || "no room"}) as ${d.dim ? "a dimmable light" : d.type}`);
}

async function update(entry: Published, d: SharedDevice) {
    const was = entry.device;
    entry.device = d;
    if (d.name !== was.name || d.room !== was.room || d.reachable !== was.reachable) await entry.info(d);
    await entry.push(d);
}

async function start(home: { name: string; id: string }) {
    Environment.default.vars.set("storage.path", STORAGE);
    Environment.default.get(StorageService);
    server = await ServerNode.create({
        // The house's own id, which rides the backup: a restored hub is the same bridge to Apple Home
        // rather than a new one with everything to add again.
        id: `home-hub-${home.id}`,
        network: { port: PORT },
        productDescription: { name: home.name, deviceType: AggregatorEndpoint.deviceType },
        basicInformation: {
            vendorName: "Home Hub",
            vendorId: VendorId(VENDOR_ID),
            productId: PRODUCT_ID,
            nodeLabel: home.name.slice(0, 32),
            // The product's name may not repeat the vendor's, and the serial may not be the unique id.
            // Both are things matter.js warns about at startup rather than refusing, which is the kind
            // of warning that survives to a certification lab if nobody reads the first run's log.
            productName: "House Bridge",
            productLabel: "House Bridge",
            serialNumber: `hub-${home.id}`,
            uniqueId: home.id,
            hardwareVersion: 1,
            hardwareVersionString: "1",
            softwareVersion: SOFTWARE_VERSION,
            softwareVersionString: VERSION,
        },
    });
    aggregator = new Endpoint(AggregatorEndpoint, { id: "house" });
    await server.add(aggregator);
    await server.start();
    server.events.commissioning.fabricsChanged.on(() => void tell());
    server.events.commissioning.commissioned.on(() => void tell());
    console.log(`the bridge is announcing as "${home.name}" on port ${PORT}`);
}

async function stop() {
    for (const entry of published.values()) await entry.close();
    published.clear();
    // Closing is not decommissioning: the fabrics stay in storage, so a household that switches
    // sharing off for a week and back on is still the same bridge to everything that holds it.
    await server?.close();
    server = aggregator = undefined;
    console.log("nothing is shared; the bridge is not announcing");
}

function status(): BridgeStatus {
    if (!server) return { running: false, commissioned: false, fabrics: [] };
    const c = server.state.commissioning;
    // The codes are reported whenever the node is actually waiting to be scanned -- which is before
    // anybody holds it, and again for as long as a window somebody asked for is open. A commissioned
    // node with a shut door has no code to show, and showing a stale one would be worse than none.
    const waiting = !c.commissioned || windowOpenUntil > Date.now();
    return {
        running: true,
        commissioned: c.commissioned,
        fabrics: Object.values(c.fabrics ?? {}).map(f => ({
            index: Number(f.fabricIndex),
            vendor: Number(f.rootVendorId),
            label: f.label ?? "",
        })),
        manual: waiting ? c.pairingCodes?.manualPairingCode : undefined,
        qr: waiting ? c.pairingCodes?.qrPairingCode : undefined,
    };
}

/**
 * Let one more app in. A Matter node takes several fabrics -- five, usually -- but only through a
 * window somebody opens deliberately: a node sitting with an open window and a printed code will join
 * whoever has the code. So the panel asks, the door stands open for the few minutes the brain names,
 * and matter.js shuts it again on its own.
 */
let windowServed = 0;          // the ask we have already acted on
let windowOpenUntil = 0;

async function openWindow(asked: number, seconds: number) {
    if (!server || asked <= windowServed) return;
    // Belt to the brain's braces: it already stops reporting an ask that has run out, and a bridge
    // that has just started has served none of them, so without one of these two a request from
    // hours ago reads as new and the door opens again on every restart. Seconds, not milliseconds --
    // the brain speaks epoch seconds.
    if (Date.now() / 1000 - asked > seconds) { windowServed = asked; return; }
    windowServed = asked;
    if (!server.state.commissioning.commissioned) return;   // nobody holds it yet; the door is already open
    try {
        await server.act(agent => agent.commissioning.enterCommissionableMode());
        windowOpenUntil = Date.now() + seconds * 1000;
        console.log(`the door is open for one more app for ${seconds} seconds`);
    } catch (e) {
        console.warn(`could not open the door: ${(e as Error).message}`);
    }
}

const tell = () => report(status());

/**
 * Fetch the list and make the bridge match it. Everything comes through here -- the first run, a
 * device changing, the household changing its mind -- because the list IS the decision, and patching
 * from a broadcast instead would let the two drift apart with nobody watching.
 */
async function reconcile() {
    if (working) { again = true; return; }
    working = true;
    try {
        const { home, devices, window: window_ } = await shared();
        if (devices.length === 0) {
            if (server) await stop();
            await tell();
            return;
        }
        if (!server) await start(home);
        if (window_.asked) await openWindow(window_.asked, window_.seconds);

        const wanted = new Set(devices.map(d => d.id));
        for (const [id, entry] of [...published]) {
            if (wanted.has(id)) continue;
            await entry.close();
            published.delete(id);
            console.log(`${entry.device.name} is no longer shared`);
        }
        for (const d of devices) {
            const entry = published.get(d.id);
            if (entry) { await update(entry, d); continue; }
            if (broken.has(d.eid)) continue;
            try { await add(d); } catch (e) {
                broken.add(d.eid);
                console.warn(`${d.name} could not be published as ${d.type}, and is left out until the bridge restarts: ${(e as Error).message}`);
            }
        }
        await tell();
    } catch (e) {
        const message = (e as Error).message;
        console.warn(`could not match the bridge to the house: ${message}`);
        await report({ ...status(), error: message });
    } finally {
        working = false;
        if (again) { again = false; void reconcile(); }
    }
}

if (!configured()) {
    console.error("no sharing key: this hub's installer predates sharing, and nothing can be published. docs/matter.md");
    process.exit(1);
}

watch(() => void reconcile());
await reconcile();
// A backstop under the stream: the brain restarts, a message is missed, and a bridge that quietly
// stopped matching the house is worse than one that is a minute late.
setInterval(() => void reconcile(), 60_000);

for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => { void server?.close().then(() => process.exit(0)); });
}
