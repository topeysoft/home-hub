# Puck rev A — current working design

Open **puck-revA.kicad_pro** in KiCad. This is the promoted pass20 design: six warm-white RGBW LEDs, four copper layers, nominal 1.6 mm thickness, and a 50 mm round board.

The KiCad schematic and routed PCB in this directory are now the authoritative editable design. Project symbols and footprints are included with project-relative library paths. Older generation scripts describe a superseded circuit and are retained only in the archived original; do not regenerate this design with those scripts.

## Status

Working design, **not approved for fabrication**. The saved pass20 DRC reports zero violations/unconnected items and the independent netlist check matches 193 pin assignments. See [validation](validation/) for the recorded reports and [remaining checks](REMAINING-CHECKS.md) for the firmware and bench-validation requirements. BOM-review.csv lists candidate parts, not an approved assembly order.

The enclosure source is preserved unchanged. Its side-button actuator height/travel, antenna installation and physical fit still require validation. The earlier B2 review flagged about 0.30 mm available travel versus up to 0.40 mm switch travel before tolerance; this promotion does not close that issue.

## Next work

- Implement the dedicated six-RGBW firmware profile and USB-C power policy.
- Confirm button/other part sourcing and USB connector assembly process.
- Validate blank-chip USB programming, current limiting, supply transients, temperatures and enclosure fit on hardware.
- Export and inspect a consistent manufacturing package after design/assembly choices are resolved. Previous Gerbers are historical and must not be used with this revision.

The promotion manifest records the original backup and intermediate-revision archive locations. No order was placed and no firmware was deployed.
