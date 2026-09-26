# Pass 20 — DRC-clean engineering review; not a manufacturing release

The original project is unchanged. This revision retains the six LEDs, four-layer board and fixed mechanical placements.

## Applied changes
- Q1/Q2: AO3400A (C20917), same SOT-23 pin order, with specified on-resistance at 2.5 V gate drive.
- R11/R18: 10 kΩ gate pull-downs instead of 100 kΩ.
- BOOT/RESET: Y78B22114FP / KMR221G ULC LFS low-current switch candidate. Shell pins added to the schematic and assigned GND on the PCB. Ground vias were added near BOOT and RESET. The RESET via is 0.45 mm diameter / 0.25 mm drill, with a short front-copper connection and a local SDA detour on the back. SCL and USB routing are unchanged.
- Supplier candidate fields imported for the fitted SMD components. The ULC buttons do not have a confirmed LCSC assembly part number. Do not substitute C72443: that is the ordinary switch variant.
- The side button already has a 2.2 kΩ pull-up; no change was needed to meet its 1 mA minimum contact current.

## Validation
- Final GUI DRC after copper refill: **0 violations, 0 unconnected items, 0 footprint errors, no ignored checks**. See DRC-pass20-final.rpt.
- Fresh schematic ERC: **0 reported errors and warnings** under the four pre-existing ignored categories listed in ERC.rpt.
- Independent schematic-to-PCB comparison after the final save: **193 connected pin assignments checked, no mismatches**.
- All 56 footprint positions and rotations are unchanged from pass18; board remains four layers. Original source PCB is unchanged.
- Failed routing trial reports are retained for traceability; only DRC-pass20-final.rpt describes the completed routing.
- A desktop lock interrupted checking temporarily. Control was restored and the completed revision was reopened, checked and saved in KiCad.

## Remaining release checks
- Confirm procurement/assembly of the two ULC buttons (special sourcing or hand fitting), the USB connector staking/solder process, and actual component stock. Supplier IDs are candidates, not a stock reservation or assembly approval.
- AO3400A improves the specified gate-drive margin, but Q2 off-state leakage and its effect on the current limiter still require temperature qualification. This revision does not establish a worst-case limit across temperature.
- Measure blank-chip computer-USB startup/programming current, supply ripple/transients and LED operation. A current-limit setting alone does not establish USB compliance or successful boot.
- Firmware power sequencing, USB behavior and thermal performance remain unvalidated on hardware.
- No new manufacturing files were released. Previous pass18 Gerbers are stale for this revision and must not be mixed with this BOM. Export and visually check a consistent set only after routing and release checks are complete.

## Sources
- [AO3400A manufacturer datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf)
- [Littelfuse KMR2 manufacturer datasheet](https://www.littelfuse.com/assetdocs/littelfuse-c-k-tactile-kmr2-series-datasheet?assetguid=f782bfc7-b600-4ab5-8c8d-a2a094a642e3)

No files have been uploaded and no order placed.
