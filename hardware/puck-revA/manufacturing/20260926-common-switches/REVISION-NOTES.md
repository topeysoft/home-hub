# Common side-actuated switches — 26 September 2026

This revision uses C&K KMS221GLFS / JLCPCB C221698 for SW1, SW2 and SW3. All three are surface-mount, side-actuated switches without positioning pegs. SW3's location, orientation and side-actuation geometry are unchanged. The footprint body lies on the PCB; the actuator is pressed parallel to the PCB through the housing. Do not substitute the GP version with pegs.

## Circuit changes

- R3: 2.2 kΩ, 0603, C4190. New R19: the same part, +3V3 to IO0.
- New R20: 300 Ω, 0603, C23025, between EN and SW2's new RESET_SW net. It limits C7's discharge through the switch.
- C7: 10 µF, 16 V, X5R, 0603, Murata GRM188R61C106KAALD / C86275, also used for C3. Nominal R3/C7 time constant is 22 ms. Actual startup delay depends on effective capacitance, temperature and supply rise.
- R8: 887 kΩ, 1%, YAGEO RC0603FR-07887KL / C246015. R16: unchanged 32.4 kΩ, 1%, sourced as UNI-ROYAL 0603WAF3242T5E / C13187.
- R19 and R20 are on the top side. Copper was added for these two resistors and the RESET branch was split at R20. The four-layer stack, six LEDs and USB routing remain unchanged.
- BOOT silkscreen moved 0.4 mm for resistor clearance. Local LED symbol footprint filters and mounting-hole BOM exclusions were brought into schematic/board agreement.

## Electrical screening

The manufacturer specifies 1 mA minimum switching current for KMS221GLFS. With 3.0 V supply and +1% resistor tolerance, BOOT current is at least 1.35 mA and RESET steady current is at least 1.19 mA. Existing SW3/R7 also provides at least 1.35 mA. This assumes GPIO0 remains an input, as intended for the boot strap.

At 3.6 V with -1% R20, initial RESET capacitor-discharge current is at most 12.13 mA, below the silver switch's 50 mA rating. R20's initial power is below 44 mW. With worst-case 1% resistor ratios, pressed EN is at most 0.123 × VDD, below the ESP32-S3 reset-low limit of 0.25 × VDD. These are circuit calculations, not prototype measurements or a full temperature qualification.

At nominal values, RESET takes approximately 5.1 ms to cross 0.25 × VDD after pressing, and approximately 28 ms to reach 0.75 × VDD after release from its steady pressed level. Hold BOOT while pressing/releasing RESET, then release BOOT after the chip enters its bootloader. Verify reset waveforms, cold startup and USB programming on the prototype; the prior firmware and USB-power limitations in REMAINING-CHECKS.md still apply.

## Validation

KiCad 10.0.6: final DRC has zero violations, zero unconnected items and zero schematic-parity issues. ERC has zero reported violations under the existing project rule settings. Existing ignored ERC categories are recorded in erc.json; no new suppressions were added. Ground planes were refilled. Two LED courtyard rounding warnings introduced by repeated KiCad saves were fixed by restoring those unchanged footprints from the previously validated board.

The assembly BOM contains 28 grouped lines, covering 52 placements, with every selected placement assigned a JLCPCB part number. The CPL was freshly exported from this PCB and checked against the BOM. J2 (optional hand-fit), J3/U5 (DNP) and mounting holes are excluded. Spreadsheet files were rendered and their saved values read back and compared with the source data. Gerbers contain all four copper layers plus masks, paste, silkscreen and outline; plated and non-plated drills are separate.

## Ordering

Use the BOM, CPL and Gerber ZIP from this directory together. Previous root-level Gerber/CSV/STEP exports and earlier stock-only BOMs predate this circuit revision and are superseded. The new files have not been uploaded or approved in JLCPCB's assembly preview. Check component orientation, especially the switches, LEDs, USB connector and ICs, in that preview before ordering. CPL angles retain KiCad's convention, normalized to 0–360 degrees; no speculative JLCPCB rotation offsets were added.

JLCPCB's live catalog showed 84 C221698 switches in stock and 81 available to order on 26 September 2026. This is not a reservation. Its catalog identifies the switch as an extended part and notes an assembly fixture requirement; confirm the quoted fixture and extended-part charges. The entire BOM's stock was not re-audited in this revision.

This is a prototype fabrication package, not evidence that the physical board has passed functional testing. Housing fit for SW1/SW2's new actuator style must be checked; SW3's mechanical placement is preserved.

## Sources

- [C&K KMS manufacturer datasheet](https://www.mouser.com/datasheet/2/240/kms-3050656.pdf)
- [JLCPCB C221698](https://jlcpcb.com/partdetail/CK-KMS221GLFS/C221698)
- [ESP32-S3-WROOM-1/1U datasheet, reset thresholds and timing](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
- [TI TUSB320 datasheet, VBUS detection resistor](https://www.ti.com/lit/ds/symlink/tusb320.pdf)
