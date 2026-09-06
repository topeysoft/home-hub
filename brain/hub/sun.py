"""Where the sun is, from the clock and the home's location. A port of app/src/sun.ts: no network, no HA.

HA's own sun.sun needs a location the engine may not have, and the panel already does this math
for the sky, so the brain does the same sums for rules.
"""
import math
from datetime import datetime, timedelta

HORIZON = -0.833   # degrees: the upper limb touches the horizon, refraction included


def elevation(when: datetime, lat: float, lon: float) -> float:
    """The sun's height above the horizon in degrees. `when` must be timezone-aware."""
    n = when.timestamp() / 86400 + 2440587.5 - 2451545.0            # days since J2000
    L = (280.46 + 0.9856474 * n) % 360                                # mean longitude
    g = math.radians((357.528 + 0.9856003 * n) % 360)                 # mean anomaly
    lam = math.radians(L + 1.915 * math.sin(g) + 0.02 * math.sin(2 * g))   # ecliptic longitude
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24
    lst = (gmst + lon / 15) % 24
    ha = math.radians(lst * 15) - ra
    ha = (ha + math.pi) % (2 * math.pi) - math.pi
    phi = math.radians(lat)
    return math.degrees(math.asin(math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(ha)))


def crossings(day_start: datetime, lat: float, lon: float, horizon: float = HORIZON):
    """Sunrise and sunset in the 24 hours from `day_start` (a local midnight), or None for each that does not happen.

    Scans the day a minute at a time and interpolates the crossing. 1440 evaluations, well under a
    millisecond; called once a day per home.
    """
    rise = set_ = None
    prev = elevation(day_start, lat, lon)
    for m in range(1, 1441):
        t = day_start + timedelta(minutes=m)
        e = elevation(t, lat, lon)
        if rise is None and prev < horizon <= e:
            rise = t - timedelta(seconds=60 * (e - horizon) / (e - prev))
        if set_ is None and prev >= horizon > e:
            set_ = t - timedelta(seconds=60 * (e - horizon) / (e - prev))
        prev = e
    return rise, set_
