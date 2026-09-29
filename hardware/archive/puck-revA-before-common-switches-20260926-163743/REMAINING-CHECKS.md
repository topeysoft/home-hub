# Prototype readiness — pass 21

This current working PCB is the promoted pass20 snapshot and retains its recorded clean DRC. This review adds a firmware compatibility audit and a concrete bench-validation plan. It does not establish that a fabricated unit will operate correctly.

## New finding: existing puck firmware is not ready for this PCB

Read-only review of `brilliant/esp32-bridge/src/light.cpp`, `src/main.cpp`, and `platformio.ini` in the home-hub checkout found:

- `rgbWrite()` transmits 24 bits for a single RGB pixel. This board requires six RGBW pixels: 192 bits per complete frame, with the chosen LED's byte order and timing verified before use.
- The S3 configuration drives GPIO48 and GPIO38 by default. A dedicated board profile must select GPIO38 only, and remove the devkit bridge-detection behavior for this board.
- The existing light driver synthesizes warm white with RGB. The new profile needs a real white-channel value for the warm-white LEDs.
- No implementation was found in the bridge source/header trees for GPIO6 LED power enable, GPIO7 data enable, GPIO10 current-limit selection, GPIO11 limiter fault, or the TUSB320 I²C controller. The default pull-downs therefore keep the LED supply and data buffer disabled under the reviewed firmware.
- Main application setup starts networking; a board-specific power policy must precede optional radio/LED loads. It cannot repair power consumed by the ROM before application code runs.

Do not use the existing devkit firmware's lack of light as evidence of a PCB fault. No firmware was changed, built, flashed or deployed during this audit. The strip firmware is a different target and was not substituted for the puck firmware.

## Board interface verified from the pass20 schematic netlist

| Function | ESP32 GPIO | U1 module pad | Required behavior |
|---|---:|---:|---|
| LED serial data | 38 | 31 | Low during power transitions; six RGBW pixels |
| LED power enable | 6 | 6 | Low until LED power is permitted |
| LED data enable | 7 | 7 | High enables Q1/buffer; low disables |
| Higher input-current limit | 10 | 18 | Low by default; high only with authorized source budget |
| Input fault | 11 | 19 | Active-low input |
| Type-C interrupt | 5 | 5 | Active-low input |
| I²C SDA | 8 | 12 | U6 controller, external pull-up present |
| I²C SCL | 9 | 17 | U6 controller, external pull-up present |
| User button | 4 | 4 | Active-low; external 2.2 kΩ pull-up |
| BOOT | 0 | 27 | Strap/recovery button, distinct from user button |
| USB D− / D+ | 19 / 20 | 13 / 14 | Native USB programming |

At application entry, latch GPIO6/7/10 and GPIO38 low before enabling their outputs. Keep data disabled while the LED rail rises; after a validated settling interval, enable data with DIN low and transmit a complete all-zero frame before a bounded light level. Disable the data driver before switching LED power off. Timing must be verified on this board, not inferred solely from an arbitrary delay.

## Type-C controller detail that the implementation must handle

The selected part is **TUSB320IRWBR**, not a similarly named LA variant. TI describes current-advertisement refresh using periodic I²C soft reset; repeatedly reading a stale current register is insufficient. Detected codes also differ from advertised codes: detected `10` is a charge-through accessory, not 3 A. The implementation needs fresh sink-attachment/current evidence, correct interrupt clearing, and conservative behavior during refresh, I²C failure or detachment. See [TI TUSB320 datasheet, sections 7.3.1.2 and 7.6](https://www.ti.com/lit/ds/symlink/tusb320.pdf).

Design policy: unknown/default source keeps high-limit mode and LEDs off. A fresh 1.5 A/3 A sink advertisement may permit the higher limit and a bounded LED budget; 3 A advertisement does not make this a 3 A board. Falling advertisement or a fault must reduce loads before reducing the current ceiling. USB enumeration/suspend policy requires separate handling; CC detection alone is not USB compliance.

## Current-limit uncertainty: what the analysis establishes

The previously calculated resistor-only limits remain approximately 351–449 mA default and 1.091–1.281 A high, including resistor tolerance. They omit Q2 leakage and other input loads. TI's ILIM programming is proportional to pin current, so off-state Q2 leakage can raise the default limit. [TPS2553 datasheet, section 9.5](https://www.ti.com/lit/ds/symlink/tps2553.pdf).

AO3400A's specified 2.5 V gate-drive resistance removes the old on-state-drive ambiguity; its 0.048 Ω figure is negligible beside R16's 32.4 kΩ. However, published off-state leakage limits at particular test temperatures/voltages do not establish this circuit's worst-case behavior throughout its intended temperature range. No unsupported extrapolation or numerical full-temperature guarantee has been made. [AO3400A datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf).

The default current setting is also a ceiling, not a guaranteed boot budget. Its minimum leaves roughly 398 mA at 3.3 V in the earlier 4.4 V / 85%-efficiency screening case, before other loads. Actual blank-chip ROM startup/programming current remains unknown. Application firmware cannot resolve a brownout that occurs before it starts.

## Bench sequence and acceptance evidence

Perform the first power and overload tests with a current-limited bench supply/USB source fixture, not a computer port. Use the USB inlet; avoid back-powering through J2/J3 while USB is connected. An electronic load can exercise SYS_5V while EN holds the ESP32 in reset. Measure total VBUS current as well as the downstream load.

| Test | Observe / record | Acceptance evidence |
|---|---|---|
| Unpowered inspection | Assembly orientation, rails-to-GND resistance, button shell continuity | No assembly shorts; correct parts and polarity |
| Controlled first power, ESP32 held reset | VBUS, SYS_5V, 3V3, GPIO6/7/10, LED_5V | Stable rails, no unexpected heating, LED controls remain low |
| Default/high current sweep | Slow electronic-load ramp, VBUS current, SYS_5V, FAULT_N | Measured limits and recovery documented; high mode exercised only on capable source |
| Q2 leakage isolation | Compare low-limit operation with Q2 gate grounded, then with R16 temporarily lifted on a designated test unit | Difference quantifies switch-branch contribution; restore and inspect afterward |
| Temperature sweep | Repeat limits at agreed enclosure operating extremes after stabilization | No source-budget violation; no unplanned shutdown. Temperature range is not yet agreed |
| Blank-chip ROM programming | Known-erased flash, native USB, both orientations, rail/current captures | Repeatable ROM enumeration and programming without brownout; no dependence on installed application firmware |
| Type-C changes | Default/1.5 A/3 A advertisement, downgrade, detach, I²C failure | Fresh source state; immediate conservative load response; no stale high-limit permission |
| RGBW output | Scope DIN and LED_5V; walk each channel on each of six LEDs at low brightness | Correct pixel order, channel order, pulse timing and power sequencing |
| Sustained operation | Radio activity plus maximum permitted light, actual enclosure and antenna | Stable rails, no resets, acceptable measured temperatures and light output |

These are required measurements, not completed test results. First establish the allowable source-current and operating-temperature envelope; compare measurements against that envelope rather than calling a near-nominal value a pass.

## Next concrete work

1. Add a separate six-RGBW puck board profile and power-control layer without changing the existing devkit target. Unit-test source-state decoding, fail-safe transitions and frame length; then build the dedicated target.
2. Resolve ULC switch procurement/hand-assembly and the remaining part-stock/USB solder-process questions.
3. Prepare one consistent pass20-derived CAM/BOM/placement set after assembly choices are fixed. Earlier pass18 Gerbers do not describe the shell-ground changes.
4. Perform the bench sequence on an engineering prototype; close full-temperature and computer-USB claims only with measurements.

This review does not place an order or approve the design for production.

## Enclosure carry-forward

The preserved B2 enclosure has an unresolved side-button travel/tolerance and actuator-height review. See README.md; verify the physical switch and antenna fit before release.
