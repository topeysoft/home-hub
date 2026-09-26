## Current revision — common side switches, 26 September 2026

SW1/SW2/SW3 now use KMS221GLFS / C221698. BOOT/RESET pull-ups, C7 and the RESET series resistor have been revised. The matching manufacturing package is `manufacturing/20260926-common-switches/`. Read its `REVISION-NOTES.md`. Earlier root-level Gerber, CSV and STEP exports are superseded. Final DRC, unrouted count, schematic parity and ERC all report zero issues under the existing project rules. This does not replace the remaining prototype and firmware tests below.

# Current PCB status

The working project is the promoted pass20 four-layer, six-RGBW design.

See [README](README.md), [remaining checks](REMAINING-CHECKS.md), and [saved design validation](validation/design-review.md). This is not a fabrication release.
