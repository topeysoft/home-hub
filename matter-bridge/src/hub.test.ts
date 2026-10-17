// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The bridge's reports to the brain. A report after every check was half of a loop that ran a hundred
 * times a second for five days: only news goes out, plus a heartbeat.
 *
 * Run with: npm test
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { teller, type BridgeStatus } from "./hub.js";

const STATUS: BridgeStatus = { running: true, commissioned: true, fabrics: [] } as unknown as BridgeStatus;

describe("reporting to the brain", () => {
    it("says the same thing once, however often it checks", async () => {
        const sent: BridgeStatus[] = [];
        let t = 0;
        const say = teller(async s => { sent.push(s); }, 50_000, () => t);
        for (let i = 0; i < 100; i++) { t += 10; await say(STATUS); }
        assert.equal(sent.length, 1);
    });

    it("says something new at once", async () => {
        const sent: BridgeStatus[] = [];
        const say = teller(async s => { sent.push(s); }, 50_000, () => 0);
        await say(STATUS);
        await say({ ...STATUS, error: "the shared list did not load" } as BridgeStatus);
        assert.equal(sent.length, 2);
    });

    it("says the same thing again once a heartbeat, so the brain knows it is alive", async () => {
        const sent: BridgeStatus[] = [];
        let t = 0;
        const say = teller(async s => { sent.push(s); }, 50_000, () => t);
        await say(STATUS);
        t = 49_999; await say(STATUS);
        t = 50_000; await say(STATUS);
        assert.equal(sent.length, 2);
    });
});
