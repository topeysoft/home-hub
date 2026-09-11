"""Regenerate tests/sun-positions.json, the table both sun implementations are held to.

Run from brain/: .venv/bin/python tests/make_sun_positions.py

Only run this when the maths is meant to change. The point of the file is that it does not move on
its own: brain/hub/sun.py and app/src/sun.ts are the same calculation written twice, and the panel's
sky and the brain's after-dark rules disagreeing is the bug it exists to catch.
"""
import json
from datetime import datetime, UTC
from pathlib import Path

from hub import sun

PLACES = [("Chicago", 41.88, -87.63), ("London", 51.51, -0.13), ("Sydney", -33.87, 151.21),
          ("Nairobi", -1.29, 36.82), ("Longyearbyen", 78.22, 15.65), ("Quito", -0.18, -78.47)]
MOMENTS = [(2026, 1, 15, 8, 0), (2026, 3, 20, 12, 0), (2026, 6, 21, 5, 30), (2026, 6, 21, 18, 45),
           (2026, 9, 11, 13, 20), (2026, 12, 21, 23, 10), (2027, 4, 2, 0, 0)]
OUT = Path(__file__).resolve().parent / "sun-positions.json"


def rows():
    for name, lat, lon in PLACES:
        for y, mo, d, hh, mm in MOMENTS:
            when = datetime(y, mo, d, hh, mm, tzinfo=UTC)
            yield {"place": name, "lat": lat, "lon": lon, "utc": when.isoformat().replace("+00:00", "Z"),
                   "elevation": round(sun.elevation(when, lat, lon), 6)}


if __name__ == "__main__":
    OUT.write_text(json.dumps({
        "_comment": "Where the sun is, computed by brain/hub/sun.py. app/src/sun.ts is a port of it and must agree "
                    "to within a thousandth of a degree; app/tests/sun.test.ts reads this same file. Regenerate with "
                    "brain/tests/make_sun_positions.py only when the maths is deliberately changed.",
        "rows": list(rows())}, indent=1) + "\n")
    print(f"wrote {OUT}")
