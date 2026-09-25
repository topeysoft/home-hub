# Puck rev A — B2 prototype PCB

The electrical design for `docs/puck-hardware.md`, at the level where drawing it in KiCad is mechanical rather than
decided. Nothing here has been fabricated. Part numbers need confirming against LCSC stock on the day you order,
and every KiCad library id below wants checking against your installed version rather than trusted.

`gen_sch.py` is the netlist below in machine-readable form, and it generates `puck-revA.kicad_sch`.
The generator is the source; the schematic is a build product, the same deal `design/puck/make-index.py`
has with `canvas.json`. **Change a net in `PARTS`, not in Eeschema** — moving symbols around in the GUI
is free and cannot break connectivity, but a wire drawn by hand will be lost on the next regeneration.

Connectivity is by global label rather than by wire routing: every pin gets a stub and a label with its
net name. That is not how a person drafts a schematic, and it is on purpose — no crossings, no
junctions, nothing that can be subtly wrong while looking right. Prettify it when the design stops
moving.

Regenerate and verify:

```sh
python3 gen_sch.py
kicad-cli sch export netlist --output puck-revA.net puck-revA.kicad_sch
python3 gen_sch.py --check puck-revA.net      # every net, against PARTS
kicad-cli sch erc --output erc.rpt --severity-error --severity-warning puck-revA.kicad_sch
```

Current verification and unresolved release checks are recorded in `PCB-STATUS.md`. The September 24 B2
update adds the side-actuated USER switch, R7 pull-up and explicit shield grounding, while preserving the
repaired routing and all enclosure-critical positions. `--check` compares all 30 functional nets with PARTS.
The generator preserves the sheet and component UUIDs across regeneration so routed footprint links survive.

ERC needs KiCad's global library tables to exist, which it writes the first time the GUI is launched.
Before that it reports a wall of `lib_symbol_issues` and `footprint_link_issues` that mean nothing —
the symbols are embedded in the schematic, so it opens and renders either way.

## The GPIO map

Assigned around the S3's fixed pins first, then the strapping pins, then convenience. The rule that generated it:
nothing that has a job at boot gets a job afterwards.

| GPIO | Net | What it does |
|---|---|---|
| `EN` | `EN` | Reset. Button to GND, 10 k to 3V3, 1 µF to GND |
| 0 | `IO0` | BOOT. Button to GND; the module has its own pull-up |
| 4 | `USER_BTN` | USER to GND; R7 2.2 kΩ external pull-up to +3V3 |
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
| `VBUS` | J1 A4/A9/B4/B9 · U2 IN · U3 VCC · D1–D11 VDD · J3 pin 2 · C1 |
| `+3V3` | U2 OUT · U1 3V3 · U5 VDD · J2 pin 4 · J3 pin 1 · C2 · C3 · R3 · R5 · R6 · R7 |
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
| `LED_DATA_5V` | U3 pin 4 (Y) · R4 (300 Ω) |
| `LED_D1_IN` | R4 · D1 DIN |
| `LED_Dn_OUT` | Dn DOUT · Dn+1 DIN, for n = 1…10 — generated in `gen_sch.py` from `N_LEDS` |
| — | D11 DOUT left unconnected |

U3's `OE` (pin 1) ties to GND so the buffer is always enabled. Four distributed 100 nF capacitors C101–C104 decouple the LED ring, matching PARTS and the actual board.
This retains the existing design choice; supply ripple and LED behavior still require prototype testing.

### I²C, buttons, headers

| Net | Connects |
|---|---|
| `SDA` | U1 IO8 · U5 SDA · R5 (4.7 kΩ to +3V3) |
| `SCL` | U1 IO9 · U5 SCL · R6 (4.7 kΩ to +3V3) |
| `USER_BTN` | U1 IO4 · SW3 to GND · R7 (2.2 kΩ to +3V3) |

**J2, the debug header** (1×4): GND, `UART0_TX` (IO43), `UART0_RX` (IO44), +3V3.

**J3, the expansion header** (1×6): +3V3, `VBUS`, GND, `EXP_A` (IO17), `EXP_B` (IO18), `EXP_C` (IO16). Rev A
populates it. The product does not, and the shell has no opening for it. The light sensor is deliberately on its own
I²C pins rather than sharing these, so an experiment on the header cannot wedge the sensor bus.

## The bill of materials

| Ref | Part | KiCad symbol | Footprint |
|---|---|---|---|
| U1 | ESP32-S3-WROOM-**1U**-N16 (or `-N16R8`) | `RF_Module:ESP32-S3-WROOM-1` (pin-identical) | `RF_Module:ESP32-S3-WROOM-1U` |
| A1 | 2.4 GHz FPC antenna, U.FL pigtail, adhesive — no footprint, it plugs into U1 | — | — |
| U2 | AP2112K-3.3, 600 mA | `Regulator_Linear:AP2112K-3.3` | `Package_TO_SOT_SMD:SOT-23-5` |
| U3 | 74AHCT1G125 | `74xGxx:74AHCT1G125` | `Package_TO_SOT_SMD:SOT-23-5` |
| U4 | USBLC6-2SC6 | `Power_Protection:USBLC6-2SC6` | `Package_TO_SOT_SMD:SOT-23-6` |
| U5 | ambient light, DNP option — **part not chosen** | `Sensor_Optical:LTR-303ALS-01` | `OptoDevice:Lite-On_LTR-303ALS-01` |
| J1 | USB-C receptacle, 16-pin, USB 2.0 | `Connector:USB_C_Receptacle_USB2.0_16P` | `Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal` |
| D1–D11 | SK6812-RGBW, 5050, on a Ø34 ring | `LED:WS2812B` (same 4 pins) | `LED_SMD:LED_SK6812_PLCC4_5.0x5.0mm_P3.2mm` |
| SW1, SW2 | BOOT, RESET — C&K KMR2, top-actuated | `Switch:SW_Push` | `Button_Switch_SMD:SW_Push_1P1T-SH_NO_CK_KMR2xxG` |
| SW3 | USER — KMS223G LFG (Y28B22310FP), side-actuated, gold, no pegs | `Puck:SW_Push_Shield` | `Button_Switch_SMD:SW_SPST_CK_KMS2xxG` |
| C1 | 22 µF, 10 V | | 0805 |
| C2 | 10 µF | | 0603 |
| C3 | 100 nF | | 0603 |
| C101–C104 | 100 nF, four distributed around the LED ring | | 0603 |
| C7 | 1 µF | | 0603 |
| R1, R2 | 5.1 kΩ | | 0603 |
| R3 | 10 kΩ | | 0603 |
| R4 | 300 Ω | | 0603 |
| R5, R6 | 4.7 kΩ | | 0603 |
| R7 | 2.2 kΩ, 1%, USER pull-up | | 0402 |

**Nothing needs drawing after all** — KiCad 10 has every symbol and footprint above. Two notes on the ones that
are not what they first look like:

- **SK6812-RGBW uses `LED:WS2812B` and a PLCC4 land.** RGBW is a fourth die, not a fifth pin: the part is still
  VDD / DOUT / VSS / DIN, which is exactly the WS2812B symbol. **Check the pin order against the datasheet for the
  part you actually buy** — the 5050 addressables disagree with each other about which corner is pin 1, and getting
  it wrong kills the chain silently.
- **The ambient light sensor is a stand-in.** KiCad 10 ships no VEML7700, so `LTR-303ALS-01` is placed — same bus,
  same job, still DNP. The part was never actually chosen; choose it rather than inheriting this.

**0603 for the original small passives; R7 is 0402.** Its smaller courtyard fits between C3 and U1
without moving them. The selected KMS has a 1 mA minimum DC contact current; 2.2 kΩ produces 1.5 mA
at 3.3 V (about 1.35 mA at 3.0 V with a +1% resistor). Its shield is explicitly grounded in PARTS and
on the PCB. BOOT/RESET shield tabs retain their original unconnected treatment and require ESD review.
Source: [KMS datasheet](https://www.ckswitches.com/media/1482/kms.pdf).

## The board file

`gen_pcb.py` generates `puck-revA.kicad_pcb` from the same `PARTS` table as the schematic, for an initial placement draft. The routed PCB is authoritative for layout; compare its pad nets to the
exported schematic after electrical changes. **It places; it does not route, and it never will.** What it fixes is the
geometry the enclosure depends on — the Ø50 outline, the three M2 holes, the eleven LEDs on their Ø34 ring, U1
at the center, J1's mouth at the 0° edge. Everything else sits on two more rings — small parts on r=12 inside the LED ring, the
switches, SOT-23s and headers on r≈22 outside it, each turned along the ring — because a grid packer cannot see
that those two annuli are the only usable shapes left on the board. Move them if you like; nothing about them is
load-bearing. B2 fixes USER at (78.8935, 106.8817) mm, -71.9417° in KiCad: about 18° away from opposite USB.
J1 remains (121.33, 100) mm at 90°. Do not move either without updating the enclosure.

```sh
python3 gen_pcb.py        # refuses to run once the board has routing in it
kicad-cli pcb drc --output drc.rpt --severity-error --severity-warning puck-revA.kicad_pcb
```

**Once you start routing, the generator stops being the source for the board.** Tracks are hand work and
re-running would erase them, so `gen_pcb.py` checks for segments, vias and zones and refuses unless you pass
`--force`. The schematic has no such hazard — it is labels and symbols, and regenerating is always safe.

The repaired routed board is now synchronized here. Do not run the placement generator with `--force`
on this project: it intentionally discards routing and does not reproduce the final placement. It is a seed
for a separate redesign only. All released mechanical dimensions come from the routed board.

## Board and fab

- 2 layers, 1.6 mm, HASL is fine, round outline about 50 mm.
- **Single-sided assembly, everything on top, LEDs included.** The shell diffuses from above. Halves the cost and
  removes a class of process risk.
- **Three M2 holes on a 44.8 mm bolt circle at {45°, 165°, 285°}**, frozen, and shared by every shell. Outside
  the ring, 7.4 mm from the nearest LED; solved against the board by `gen_pcb.py` rather than chosen.
- Actual project rules currently permit 0.127 mm track/clearance (0.2 mm power clearance), 0.15 mm drills,
  0.25 mm vias and 0.05 mm annular rings. They are inherited autorouter limits, not a conservative process approval.
  JLCPCB publishes these small via limits, but selected stackup, tolerances, finish and assembly options still need review.
- New USB/ground repair vias are 0.4/0.2 mm; the small inherited USB vias remain a manufacturing review item.
- The ESP32-S3-WROOM-1U uses an external U.FL flex antenna. There is no module trace antenna hanging over
  the PCB edge. Mount the selected antenna inside the diffuser with its supplier's metal clearance, orientation
  and cable requirements; validate RF performance in the assembled B2 shell.
- B2 is 58 mm diameter, 20 mm high. PCB underside is nominally 5.6 mm above the base and board thickness is 1.6 mm.
  USER actuator center height remains provisional; verify the exact part/sample before releasing the 7.95 mm bore height.

## Bring-up, in order

Each step is a thing that can fail on its own. Do not skip ahead — a board that enumerates but browns out under
Wi-Fi TX looks exactly like a firmware bug.

1. **The 3.3 V rail**, on a bench supply through the USB-C, before the module is trusted with anything.
2. **USB enumeration.** A `/dev/cu.usbmodem*` appearing is the whole test.
3. **Flash the existing `esp32s3-ship` image** with `-DBRIDGE_RGB_PIN=38` added.
4. **The light**, all four states by hand over the cable console: `set night 1 <level>`, and the three instrument
   states.
5. **A BLE scan beside a real switch**, with `tools/bridge_watch.py` open. This is the first moment the antenna placement is validated in the assembled enclosure.
6. **Then the four questions in `docs/puck-hardware.md`**, in a house, with the three shells.
