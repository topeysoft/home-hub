#!/usr/bin/env python3
"""Coverage may go up. It may not go down.

There is no target to reach and nothing to game: the only rule is that a change does not leave the
codebase less covered than it found it. Reads coverage.xml (the brain) and coverage-summary.json
(the panel), compares against .github/coverage-floor.json, and says what to do when it has risen.

Usage: coverage-check.py brain brain/coverage.xml
       coverage-check.py panel app/coverage/coverage-summary.json
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FLOORS = ROOT / "coverage-floor.json"


def measured(part: str, path: Path) -> float:
    if part == "brain":
        # coverage.py's XML: line-rate on the root element, as a fraction.
        return float(ET.parse(path).getroot().get("line-rate")) * 100
    return float(json.loads(path.read_text())["total"]["statements"]["pct"])


def main() -> int:
    part, path = sys.argv[1], Path(sys.argv[2])
    if not path.exists():
        print(f"::error::no coverage report at {path}; the test step did not produce one")
        return 1

    floors = json.loads(FLOORS.read_text())
    floor, now = float(floors[part]), measured(part, path)
    where = f"{part}: {now:.1f}% covered (floor {floor:.1f}%)"

    if now + 0.05 < floor:
        print(f"::error::{where} — this change covers less than what it started from. "
              f"Add tests for what it touched, or say why in the pull request.")
        return 1

    print(f"{where} ✓")
    if now >= floor + 1:
        print(f"::notice::{part} coverage is now {now:.1f}%, {now - floor:.1f} points above its floor. "
              f"Raise \"{part}\" in .github/coverage-floor.json to {int(now)} to keep it there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
