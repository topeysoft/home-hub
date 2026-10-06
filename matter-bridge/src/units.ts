// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * EVERY conversion between the house's way of saying a thing and Matter's lives here, together, and
 * nothing above this line thinks in Matter's units. Each one of these is a way to ship a blind that
 * opens when it should close, so they are written once, named, and used from one place each.
 */
// Matter's level is 1..254 and Home Assistant's brightness is 0..255, and the brain is asked in per
// cent because that is what its own route takes (`brightness_pct`, the way the panel dims).
export const toLevel = (brightness: number | null) => Math.max(1, Math.min(254, Math.round(((brightness ?? 255) / 255) * 254)));
export const toPercent = (level: number) => Math.max(1, Math.min(100, Math.round((level / 254) * 100)));

// Matter speaks centi-Celsius everywhere a temperature appears. The house speaks whatever it speaks.
export const toC = (v: number, unit: string) => (unit.includes("F") ? ((v - 32) * 5) / 9 : v);
export const fromC = (v: number, unit: string) => (unit.includes("F") ? (v * 9) / 5 + 32 : v);
export const toCenti = (v: number | null | undefined, unit: string) => (v == null ? null : Math.round(toC(v, unit) * 100));
export const fromCenti = (v: number, unit: string) => Math.round(fromC(v / 100, unit) * 10) / 10;

// THE INVERSION. Home Assistant counts a cover from open -- 100 is fully open. Matter's
// LiftPercent100ths counts from the other end: 0 is fully open and 10000 is fully closed.
export const toLift = (position: number | null | undefined) => Math.max(0, Math.min(10000, Math.round((100 - (position ?? 100)) * 100)));
export const fromLift = (lift: number) => Math.max(0, Math.min(100, Math.round(100 - lift / 100)));

// Matter's humidity is centi-per-cent, like its temperatures.
export const toCentiPct = (v: number | null | undefined) => (v == null ? null : Math.max(0, Math.min(10000, Math.round(v * 100))));

// HA's hvac modes against Matter's SystemMode. `heat_cool` and `auto` are both Matter's Auto; a mode
// this house has that Matter has not (`dry`, `fan_only`) reads as Off, which is the honest answer --
// Matter has no word for it, and inventing one would tell Apple Home something untrue.
export const MODE_TO_MATTER: Record<string, number> = { off: 0, auto: 1, heat_cool: 1, cool: 3, heat: 4 };
export const MODE_FROM_MATTER: Record<number, string> = { 0: "off", 1: "heat_cool", 3: "cool", 4: "heat" };
