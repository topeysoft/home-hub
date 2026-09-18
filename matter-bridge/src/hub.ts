/**
 * The brain, as this container sees it.
 *
 * The bridge does no thinking about the house: it asks for a list and publishes it, posts a command
 * back when a commissioner sends one, and says what it is. Everything that decides WHAT may be shared
 * lives in `brain/hub/share.py`, where the rules have tests. See `docs/matter.md`.
 *
 * It is not a phone, so it does not have a phone's cookie. It carries the key install.sh gave both
 * containers, on the header the brain's middleware knows, and that key opens `/share/bridge/` and
 * nothing else.
 */
import WebSocket from "ws";

const HUB = process.env.HUB_URL ?? "http://localhost:8300";
const TOKEN = process.env.HUB_SHARE_TOKEN ?? "";
const HEADER = "x-hub-service";

export type SharedType =
    | "light" | "plug" | "fan" | "cover" | "thermostat" | "lock"
    | "occupancy" | "contact" | "temperature" | "humidity";

/** Everything is in the HOUSE's units and conventions: degrees in whatever the house speaks, a cover
 *  position counted from open the way Home Assistant counts it, a contact that is `open` when the door
 *  is open. Matter wants centi-Celsius, a lift percentage counted from the other end, and a contact
 *  whose `true` means shut -- and every one of those conversions lives in `main.ts`, beside the cluster
 *  it belongs to, so the trap is never two files away from the thing it would spring on. */
export interface SharedDevice {
    id: string;          // the brain's device id: what a command is posted back to
    eid: string;         // this bridge's stable name for it; the Matter endpoint number is remembered against it
    type: SharedType;
    kind: string;
    dim: boolean;
    unit: string;        // the house's temperature unit, "°F" or "°C", both ways
    name: string;
    room: string;
    maker: string;
    reachable: boolean;
    state: {
        on?: boolean;
        brightness?: number | null;
        percent?: number | null;
        position?: number | null;      // 100 is fully open, the way Home Assistant counts it
        locked?: boolean;
        known?: boolean;               // a lock whose state the driver is unsure of
        detected?: boolean;
        open?: boolean;                // a contact: true when the door is OPEN
        value?: number | null;
        mode?: string;
        target?: number | null;
        target_low?: number | null;
        target_high?: number | null;
        current?: number | null;
        min?: number | null;
        max?: number | null;
        modes?: string[];
    };
}

export interface SharedHouse {
    home: { name: string; id: string };
    /** When the panel last asked for the door to be opened for one more app, and for how long. */
    window: { asked: number | null; seconds: number };
    devices: SharedDevice[];
}

/** One app holding this house. The bridge reports the vendor id and the label and names neither:
 *  who a vendor id belongs to is a fact from the CSA's ledger, and it lives in `share.py` with a
 *  test, because a wrong name here would tell somebody the wrong app is in their house. */
export interface Fabric {
    index: number;
    vendor: number;
    label: string;
}

export interface BridgeStatus {
    running: boolean;
    commissioned: boolean;
    fabrics: Fabric[];
    manual?: string;
    qr?: string;
    error?: string;
}

function headers(): Record<string, string> {
    return { [HEADER]: TOKEN, "content-type": "application/json" };
}

export async function shared(): Promise<SharedHouse> {
    const r = await fetch(`${HUB}/share/bridge/devices`, { headers: headers() });
    if (!r.ok) throw new Error(`the brain answered ${r.status} for the shared list`);
    return (await r.json()) as SharedHouse;
}

/**
 * A command that arrived through somebody else's assistant. The brain runs it the way it runs a tap,
 * which is the point: the driver's own service is still chosen there, by `capability`, so a re-typed
 * lamp on a plug is still switched as the plug it is. A refusal is normal rather than exceptional --
 * the house may have stopped sharing the thing since the list was fetched -- so it is logged and dropped.
 */
export async function act(id: string, action: string, data?: Record<string, unknown>): Promise<boolean> {
    const r = await fetch(`${HUB}/share/bridge/act/${encodeURIComponent(id)}/${action}`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(data ?? null),
    });
    if (!r.ok) console.warn(`${id} ${action}: the house said no (${r.status})`);
    return r.ok;
}

/** What the panel shows about this bridge while it waits to be scanned, and once it is held. */
export async function report(status: BridgeStatus): Promise<void> {
    try {
        await fetch(`${HUB}/share/bridge/status`, { method: "POST", headers: headers(), body: JSON.stringify(status) });
    } catch (e) {
        console.warn(`could not tell the brain how the bridge is: ${(e as Error).message}`);
    }
}

/**
 * The same broadcasts the panels watch. A device changing, or the household changing its mind about
 * what is shared, both arrive here; either way the answer is to reconcile against a fresh list rather
 * than to patch from the message, because the list IS the decision and a message is only a nudge.
 */
export function watch(onNudge: () => void): void {
    const url = `${HUB.replace(/^http/, "ws")}/stream`;
    let ws: WebSocket | undefined;
    const open = () => {
        ws = new WebSocket(url, { headers: { [HEADER]: TOKEN } });
        ws.on("message", raw => {
            let msg: { type?: string };
            try { msg = JSON.parse(String(raw)); } catch { return; }
            if (msg.type === "device" || msg.type === "share" || msg.type === "home") onNudge();
        });
        ws.on("error", e => console.warn(`stream: ${e.message}`));
        // The brain restarts more often than this container does -- an update installs in the night --
        // so a dropped stream is an ordinary event and not a failure to report.
        ws.on("close", () => setTimeout(open, 3000));
    };
    open();
}

export function configured(): boolean {
    return TOKEN.length > 0;
}
