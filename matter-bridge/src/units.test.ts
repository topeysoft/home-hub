// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The conversions, and three of them are INVERSIONS -- the ways this bridge would most quietly ship a
 * blind that opens when it should close, a thermostat reading 22 when the house said 71, or a door
 * reported shut while it stands open. None of that shows up in a typecheck and none of it shows up
 * until somebody is standing in front of the thing.
 *
 * Run with: npm test
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { fromCenti, fromLift, MODE_FROM_MATTER, MODE_TO_MATTER, toCenti, toCentiPct, toLevel, toLift, toPercent } from "./units.js";

describe("a cover's position", () => {
    it("counts from the other end than the house does", () => {
        // Home Assistant: 100 is fully OPEN. Matter: 0 is fully open, 10000 fully closed.
        assert.equal(toLift(100), 0);
        assert.equal(toLift(0), 10000);
        assert.equal(toLift(70), 3000);
    });

    it("comes back the way it went", () => {
        for (const position of [0, 1, 35, 70, 99, 100]) assert.equal(fromLift(toLift(position)), position);
    });

    it("treats a cover with no position of its own as open", () => {
        // A garage door has no position; the brain sends null and the honest answer is not "closed".
        assert.equal(toLift(null), 0);
        assert.equal(toLift(undefined), 0);
    });
});

describe("a temperature", () => {
    it("leaves a Fahrenheit house as centi-Celsius", () => {
        assert.equal(toCenti(32, "°F"), 0);
        assert.equal(toCenti(212, "°F"), 10000);
        assert.equal(toCenti(71, "°F"), 2167);
    });

    it("is left alone where the house already speaks Celsius", () => {
        assert.equal(toCenti(21.5, "°C"), 2150);
    });

    it("comes back in the house's own scale, because that is what the driver takes", () => {
        assert.equal(fromCenti(2167, "°F"), 71);
        assert.equal(fromCenti(2150, "°C"), 21.5);
        // ...and a dial dragged in Apple Home lands back within a tenth of where it started
        for (const t of [60, 68, 71.5, 75, 80]) assert.ok(Math.abs(fromCenti(toCenti(t, "°F")!, "°F") - t) <= 0.1);
    });

    it("says nothing rather than zero when there is no reading", () => {
        assert.equal(toCenti(null, "°F"), null);
        assert.equal(toCenti(undefined, "°C"), null);
    });
});

describe("a humidity", () => {
    it("is centi-per-cent, and absent when unread", () => {
        assert.equal(toCentiPct(41.5), 4150);
        assert.equal(toCentiPct(0), 0);
        assert.equal(toCentiPct(null), null);
    });
});

describe("a light's level", () => {
    it("maps Home Assistant's 0..255 onto Matter's 1..254 and never reaches zero", () => {
        // Matter has no level 0: off is the OnOff cluster's business, not the level's.
        assert.equal(toLevel(0), 1);
        assert.equal(toLevel(255), 254);
        assert.equal(toLevel(null), 254);
        assert.ok(toLevel(1) >= 1);
    });

    it("is asked back in per cent, because that is the route the panel uses", () => {
        assert.equal(toPercent(254), 100);
        assert.equal(toPercent(127), 50);
        assert.equal(toPercent(1), 1);          // never 0: a 0% "on" is an off with extra steps
    });
});

describe("a thermostat's mode", () => {
    it("carries the modes Matter has a word for", () => {
        assert.equal(MODE_TO_MATTER.off, 0);
        assert.equal(MODE_TO_MATTER.heat, 4);
        assert.equal(MODE_TO_MATTER.cool, 3);
        assert.equal(MODE_TO_MATTER.heat_cool, 1);
        assert.equal(MODE_FROM_MATTER[4], "heat");
    });

    it("reads a mode Matter has no word for as off rather than inventing one", () => {
        // `dry` and `fan_only` exist in plenty of houses and nowhere in Matter's SystemMode.
        assert.equal(MODE_TO_MATTER.dry, undefined);
        assert.equal(MODE_TO_MATTER.fan_only, undefined);
    });
});
