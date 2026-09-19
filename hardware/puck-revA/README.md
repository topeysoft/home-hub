# Puck rev A — the buildable spec

The electrical design for `docs/puck-hardware.md`, at the level where drawing it in KiCad is mechanical rather than
decided. Nothing here has been fabricated. Part numbers need confirming against LCSC stock on the day you order,
and every KiCad library id below wants checking against your installed version rather than trusted.

KiCad project files land in this directory when they exist.

## The GPIO map

Assigned around the S3's fixed pins first, then the strapping pins, then convenience. The rule that generated it:
nothing that has a job at boot gets a job afterwards.

| GPIO | Net | What it does |
|---|---|---|
| `EN` | `EN` | Reset. Button to GND, 10 k to 3V3, 1 µF to GND |
| 0 | `IO0` | BOOT. Button to GND; the module has its own pull-up |
| 4 | `USER_BTN` | The user button, to GND, internal pull-up |
| 8 | `SDA` | I²C to the light sensor |
| 9 | `SCL` | I²C to the light sensor |
| 16 | `EXP_C` | Expansion header |
| 17 | `EXP_A` | Expansion header — LD2410 TX, or an AM312's OUT |
| 18 | `EXP_B` | Expansion header — LD2410 RX |
| 19 | `USB_DM` | USB D−. Fixed by the silicon |
| 20 | `USB_DP` | USB D+. Fixed by the silicon |
| 38 | `LED_DATA_3V3` | To the level shifter's input |
| 43 | `UART0_TX` | Debug header |
| 44 | `UART0_RX` | Debug header |

**Not available, and why.** GPIO26–32 are the SPI flash. GPIO33–37 go to octal PSRAM on an `-N16R8` and are simply
absent on that part. GPIO3, 45 and 46 are strapping pins. GPIO48 is deliberately left unconnected: it is the old
devkit LED pin, and leaving it floating means `detectBridge()` in `light.cpp` reads the two candidates as separate
and behaves, on the chance this board is ever flashed with a devkit build.

**GPIO38 for the LED is not arbitrary.** It is already one of the two pins `light.cpp` drives, so
`-DBRIDGE_RGB_PIN=38` collapses `RGB_PINS[]` to one entry, `detectBridge()` returns early, and the dual-drive
workaround becomes dead code on this target without touching the devkit environments.

## The netlist

### Power

| Net | Connects |
|---|---|
| `VBUS` | J1 A4/A9/B4/B9 · U2 IN · U3 VCC · D1–D3 VDD · J3 pin 2 · C1 |
| `+3V3` | U2 OUT · U1 3V3 · U5 VDD · J2 pin 4 · J3 pin 1 · C2 · C3 · R3 · R5 · R6 |
| `GND` | everything, including U1's exposed pad, which is a thermal *and* electrical connection |

C1 22 µF on VBUS, C2 10 µF and C3 100 nF at U1's 3V3 pin and as close to it as the layout allows.

### USB

| Net | Connects |
|---|---|
| `USB_DM` | J1 A7/B7 · U4 · U1 IO19 |
| `USB_DP` | J1 A6/B6 · U4 · U1 IO20 |
| `CC1` | J1 A5 · R1 (5.1 kΩ) · GND |
| `CC2` | J1 B5 · R2 (5.1 kΩ) · GND |
| `SHIELD` | J1 shell · GND |

**R1 and R2 are the part everybody forgets.** Without them a C-to-C cable delivers no power at all while an A-to-C
cable works, so the board looks intermittent rather than broken. They are not optional and they are not shared —
each CC pin gets its own.

### Reset and boot

| Net | Connects |
|---|---|
| `EN` | U1 EN · R3 (10 kΩ to +3V3) · C7 (1 µF to GND) · SW2 to GND |
| `IO0` | U1 IO0 · SW1 to GND |

### The LED chain

| Net | Connects |
|---|---|
| `LED_DATA_3V3` | U1 IO38 · U3 pin 2 (A) |
| `LED_DATA_5V` | U3 pin 4 (Y) · R4 (300 Ω) · D1 DIN |
| `D1_DOUT` | D1 DOUT · D2 DIN |
| `D2_DOUT` | D2 DOUT · D3 DIN |
| — | D3 DOUT left unconnected |

U3's `OE` (pin 1) ties to GND so the buffer is always enabled. 100 nF across each LED's VDD/GND, each one placed at
its own part rather than pooled.

### I²C, buttons, headers

| Net | Connects |
|---|---|
| `SDA` | U1 IO8 · U5 SDA · R5 (4.7 kΩ to +3V3) |
| `SCL` | U1 IO9 · U5 SCL · R6 (4.7 kΩ to +3V3) |
| `USER_BTN` | U1 IO4 · SW3 to GND |

**J2, the debug header** (1×4): GND, `UART0_TX` (IO43), `UART0_RX` (IO44), +3V3.

**J3, the expansion header** (1×6): +3V3, `VBUS`, GND, `EXP_A` (IO17), `EXP_B` (IO18), `EXP_C` (IO16). Rev A
populates it. The product does not, and the shell has no opening for it. The light sensor is deliberately on its own
I²C pins rather than sharing these, so an experiment on the header cannot wedge the sensor bus.

## The bill of materials

| Ref | Part | KiCad symbol | Footprint |
|---|---|---|---|
| U1 | ESP32-S3-WROOM-1-**N16** (or `-N16R8`) | `RF_Module:ESP32-S3-WROOM-1` | `RF_Module:ESP32-S3-WROOM-1` |
| U2 | AP2112K-3.3, 600 mA | `Regulator_Linear:AP2112K-3.3` | `Package_TO_SOT_SMD:SOT-23-5` |
| U3 | 74AHCT1G125 | `74xGxx:74AHCT1G125` | `Package_TO_SOT_SMD:SOT-23-5` |
| U4 | USBLC6-2SC6 | `Power_Protection:USBLC6-2SC6` | `Package_TO_SOT_SMD:SOT-23-6` |
| U5 | VEML7700 — ambient light, DNP option | likely needs drawing | per datasheet |
| J1 | USB-C receptacle, 16-pin, USB 2.0 | `Connector:USB_C_Receptacle_USB2.0_16P` | per chosen MPN |
| D1–D3 | SK6812-RGBW, 5050 | likely needs drawing | `LED:LED_SK6812_PLCC6_5.0x5.0mm` |
| SW1–SW3 | BOOT, RESET, USER | `Switch:SW_Push` | side-actuated SMD |
| C1 | 22 µF, 10 V | | 0805 |
| C2 | 10 µF | | 0603 |
| C3–C6 | 100 nF | | 0603 |
| C7 | 1 µF | | 0603 |
| R1, R2 | 5.1 kΩ | | 0603 |
| R3 | 10 kΩ | | 0603 |
| R4 | 300 Ω | | 0603 |
| R5, R6 | 4.7 kΩ | | 0603 |

**On the two that need drawing.** SK6812-RGBW and VEML7700 are not reliably in the stock libraries. SK6812-RGBW is
close enough to WS2812B to share a land pattern if you draw the symbol for it — but check the pin order on the
datasheet you are actually buying against, because the 5050 addressables disagree with each other about which
corner is pin 1, and getting it wrong bricks the chain silently.

**0603 throughout**, not 0402. JLC places either, but five boards and a soldering iron in the room means the ability
to rework matters more than the millimeter, and nothing here is space-constrained on a 50 mm disc.

## Board and fab

- 2 layers, 1.6 mm, HASL is fine, round outline about 50 mm.
- **Single-sided assembly, everything on top, LEDs included.** The shell diffuses from above. Halves the cost and
  removes a class of process risk.
- **Three M2 holes on one bolt circle, frozen when the outline is.** This is what makes "one board, several shells"
  real. Pick the circle once and never move it.
- Conservative rules well inside JLC's standard process: 0.152 mm track and clearance, 0.3 mm drill with 0.6 mm pad.
  Confirm against their current capability page before ordering rather than trusting these.
- Extended parts carry a per-part setup fee. U1, U3, D1–D3 and probably J1 will all be extended.

**The antenna keepout is placed before anything else, not fitted around the layout afterwards.** U1's antenna end
overhangs the board edge; zero copper on every layer beneath it; no ground pour, no traces, no vias. The USB-C goes
at the opposite edge, because the cube and its cable are the nearest metal this object will ever have.

## Bring-up, in order

Each step is a thing that can fail on its own. Do not skip ahead — a board that enumerates but browns out under
Wi-Fi TX looks exactly like a firmware bug.

1. **The 3.3 V rail**, on a bench supply through the USB-C, before the module is trusted with anything.
2. **USB enumeration.** A `/dev/cu.usbmodem*` appearing is the whole test.
3. **Flash the existing `esp32s3-ship` image** with `-DBRIDGE_RGB_PIN=38` added.
4. **The light**, all four states by hand over the cable console: `set night 1 <level>`, and the three instrument
   states.
5. **A BLE scan beside a real switch**, with `tools/bridge_watch.py` open. This is the first moment the antenna
   keepout is either right or was not.
6. **Then the four questions in `docs/puck-hardware.md`**, in a house, with the three shells.
