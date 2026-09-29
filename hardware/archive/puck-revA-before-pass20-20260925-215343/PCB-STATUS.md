# B2 PCB synchronization — 24 September 2026

This is an engineering prototype update, not a fabrication release. The September 24 repaired board was
reconciled with the repository schematic source. Existing routing and all existing footprint placements were
preserved, except the SW3 package was replaced in place by its pad-compatible side-actuated version.

## Changes and evidence

- SW3: KMS223G LFG / Littelfuse Y28B22310FP, gold contacts, no pegs, nominal 2 N. The installed KMS and
  KMR2 footprints have identical five pad numbers, positions and sizes. Its existing rotation faces outward.
- R7: 2.2 kΩ, 1%, 0402 between +3V3 and USER_BTN; center (89.75,95.95), rotation 90°. Nominal closed-switch
  current is 1.5 mA, about 1.35 mA at 3.0 V and +1% resistance, exceeding the datasheet's 1 mA minimum.
  The 0402 package clears existing courtyards where 0603 did not. One 0.6/0.3 mm GND via joins the pour
  split by this new route. No other component was moved.
- Puck:SW_Push_Shield and the project symbol table make the SW3 shield connection explicit in PARTS.
  BOOT/RESET retain their previous unconnected shield tabs; their ESD treatment remains a review item.
- H1–H3 are now represented in the schematic; all explicit unused-pin net names are assigned on the PCB.
- gen_sch.py retains sheet/component UUIDs on regeneration. The exported netlist matches all 30 intended
  functional nets. verify_sync.py checks all 40 components and 171 exported pin assignments, footprint IDs,
  values and schematic UUID links, with zero differences.
- KiCad GUI DRC with zone refill: **0 errors, 0 unconnected, 34 warnings**. Before this update the repaired
  board had 0 errors, 0 unconnected and 35 warnings. The remaining 34 are 29 silkscreen issues and 5 library
  footprint mismatches (C1, J2, J3, SW1, SW2). No blanket library update was applied to the routed board.
- Schematic ERC: **0 errors, 0 warnings**. Four inherited ERC checks remain ignored, as listed in erc.rpt.
- GUI schematic-parity test was unavailable in the standalone editor; CLI PCB DRC crashes on this Mac.
  The explicit exported-net/component comparison above passed, but is not claimed as a native parity result.
  Five inherited DRC ignored categories remain listed in DRC-b2-final.rpt.

Reports: DRC-b2-final.rpt, erc.rpt, sync-check.json. Regenerate/export after.net before running verify_sync.py.

## Frozen enclosure references

| Item | KiCad X, Y (mm) | Rotation |
|---|---|---|
| USER/SW3 | 78.8935, 106.8817 | -71.9417° |
| USB/J1 | 121.33, 100 | 90° |
| H1 | 115.8392, 84.1608 | unchanged |
| H2 | 78.3633, 94.2025 | unchanged |
| H3 | 105.7975, 121.6367 | unchanged |

Board diameter 50 mm; thickness 1.6 mm. B2 exterior 58 × 20 mm; PCB underside nominally Z=5.6 mm.
The switch pad change needs no XY enclosure adjustment. Its actuator height and travel tolerance still need
verification against the exact part/sample; retain the provisional bore height Z=7.95 mm until then.
The KMS223G travel is 0.25 ±0.15 mm; B2 currently provides about 0.30 mm after its tip gap. That is
0.10 mm short of the switch maximum travel before tolerances, so the enclosure travel budget needs revision
or validation with a tighter supplier specification before release. R7 is
inside the existing component envelope, but the enclosure reference model should be refreshed for the new BOM.

## Manufacturing and electrical blockers

1. Full USB pair signal integrity: the inherited routes are separated, include detours and small vias, and
   have not been impedance-qualified or length-matched. Connectivity repair alone does not validate USB.
2. Confirm the JLCPCB stackup/process and tolerances. Current inherited limits are 0.127 mm track/clearance,
   0.2 mm power clearance, 0.15 mm minimum drill, 0.25 mm via diameter, 0.05 mm annular ring. JLCPCB's current
   rigid capabilities publish 0.15/0.25 mm vias, but process review, via-in-pad treatment and assembly review
   are still required. No thresholds were relaxed in this update.
3. USB-C power/current behavior: the board still uses separate 5.1 kΩ Rd resistors. The TUSB320 draft is NOT
   integrated. Final charger rating, current-advertisement handling, inrush, LED budget and thermal validation
   remain unresolved. Do not assume C-to-C alone authorizes a 3 A load.
4. Exact LED ordering code/pinout/current, sensor DNP choice and regulator transient/thermal margin need final
   review. Four distributed LED capacitors are retained; measure supply ripple and nightlight temperature.
5. Resolve the five library mismatches and silkscreen warnings, review native schematic parity in the project,
   and validate the selected switch, antenna, plunger travel and cable fit in physical prototypes.
6. The KMS223G LFG is listed as orderable by the manufacturer and has a distributor listing; no stock is
   reserved and JLCPCB/LCSC assembly sourcing is not confirmed. Choose procurement before release.

## Sources

- [KMS datasheet](https://www.ckswitches.com/media/1482/kms.pdf): side actuation, ordering code, current and travel.
- [KMS223G LFG distributor listing](https://www.digikey.com/en/products/detail/c-k/Y28B22310FP/2043220).
- [JLCPCB rigid capabilities](https://jlcpcb.com/capabilities/Capab).

Backups of the pre-sync repository files are retained in the PCB task's work/b2-backup directory and the
B2 synchronization backup archive. Do not use gen_pcb.py --force on the routed board.
