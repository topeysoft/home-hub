// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// What keeps a rev A strip controller from hurting itself, a strip, or a house -- on the board, with
// nobody asking.
//
// THE BOX TAKES ANY SUPPLY FROM 5 TO 24 V AND CANNOT KNOW WHAT IS PLUGGED INTO ITS RUNS. A 12 V strip
// given a 24 V supply is a strip on fire, and the board has no way to ask a strip what it is. What it
// can do is notice a CHANGE: it measures the supply before either run is switched on, remembers what
// each run was first lit on, and on any later boot refuses to light a run whose supply is now a
// different kind. The hardware's own cutoffs (below 4.2 V, above 30.1 V) are a second line under
// this one, not the line.
//
// AND IT DIMS RATHER THAN TRIPS. Each run's switch cuts at 5.07 A at the low end of its tolerance and
// retries 650 ms later, which from across a room is a light that flashes off and on. So the firmware
// predicts each frame's current from its pixels before it is sent, sends it dimmed if it would draw
// too much, and corrects the prediction from what the switch's current monitor actually reads. The
// trip is there for a short circuit; it is never the thing that holds a bright picture down.
//
// Nothing here relies on the hub, and nothing here waits for it: a strip in a house whose hub is down
// is exactly as safe. The hub is only TOLD (`power`, below), so the wall can say why a run is dark.
//
// The arithmetic is above the line and free of ESP-IDF, so test_guard_native.cpp holds it to the
// numbers on a Mac. guard.cpp is the half that reads pins.
#pragma once

#include <math.h>
#include <stddef.h>
#include <stdint.h>

#include "board.h"
#include "pixels.h"

namespace guard {

// ---------------------------------------------------------------- what the supply is

// The three kinds of supply a strip is sold for, and NONE for anything else.
enum Class : uint8_t { NONE = 0, V5 = 5, V12 = 12, V24 = 24 };

// THE WINDOWS ARE WIDE ON PURPOSE. The reading is good to about 0.2 V, and a supply is measured with
// both runs off, so it is not sagging under a strip: a 5 V brick reads 5.0-5.3, a 12 V one anything
// from 10.8 to 13.2, and a 24 V one from 21.6 to the 28.8 V some are trimmed up to. What falls
// BETWEEN windows -- a 9 V adapter, a 19 V laptop brick -- is nothing a strip is made for, and is
// treated as out of range rather than rounded to the nearest kind. Below 4.3 V the switches
// themselves will not run a strip properly; above 30 V the board's own cutoff has already darkened
// both runs.
static inline uint8_t classify(float volts)
{
    if (volts >= 4.3f && volts <= 6.5f) return V5;
    if (volts >= 10.0f && volts <= 15.5f) return V12;
    if (volts >= 21.0f && volts <= 30.0f) return V24;
    return NONE;
}

// WHY A RUN IS DARK, if it is. FREE is lit as asked; the rest are the reasons the board said no, and
// each is a different sentence on the wall.
enum Held : uint8_t {
    FREE = 0,
    STARTING,   // the supply has not yet read the same twice; nothing is lit until it has
    RANGE,      // the supply is out of range, or between kinds
    SUPPLY,     // a different kind of supply from the one this run was first lit on
    TRIPS,      // its switch kept cutting it: a short, or a strip that draws more than any dimming fixes
    WIRING,     // something above ~6 V is on its DATA or CLK line: a miswired plug
};

static inline const char *held_word(uint8_t h)
{
    switch (h) {
    case FREE: return "";
    case STARTING: return "starting";
    case RANGE: return "range";
    case SUPPLY: return "supply";
    case TRIPS: return "trips";
    case WIRING: return "wiring";
    default: return "?";
    }
}

// THE DECISION, FOR ONE RUN, AT BOOT. `kept` is the class the run was first lit on, from NVS, or NONE
// for a run that has never been lit.
//
// THE VERY FIRST TIME, THERE IS NOTHING TO COMPARE WITH, and the board says so honestly: a run that
// has never been lit is lit on whatever supply it finds, if that supply is one of the three kinds,
// and that kind is written down the moment it is switched on (guard.cpp). There is no earlier moment
// to choose: a new strip glows the instant it has power, because the glow is how a household knows
// which thing is asking to be set up, and the board cannot tell a 12 V strip from a 24 V one before
// it is lit. So it is the first lighting that fixes what the run expects; after that a different kind
// of supply leaves it dark and says why. Forgetting the house -- the hold on the button, or the panel
// -- erases the record with everything else, which is the same gesture as giving the strip a new
// home, and is the only way to move a run to a different supply.
static inline uint8_t may_light(uint8_t now, uint8_t kept)
{
    if (now == NONE) return RANGE;
    if (kept != NONE && kept != now) return SUPPLY;
    return FREE;
}

// ---------------------------------------------------------------- what the pins read

#if defined(STRIP_BOARD_REVA)   // the dividers are rev A's; a devkit has nothing to read
static inline float supply_volts(int mv) { return mv * board::VSENSE_RATIO / 1000.0f; }

static inline float imon_amps(int mv) { return mv / 1000.0f / board::IMON_V_PER_A; }
#endif

// THE BOARD'S TEMPERATURE, from the NTC: 10k at 25 C, B 3435, to ground under a 10k pull-up. NaN
// when the reading is pinned to either rail, which is a thermistor that is open or shorted rather
// than a board at -60 or +200 C.
static inline float ntc_celsius(int mv, float rail_mv)
{
    if (mv <= 20 || mv >= rail_mv - 20) return NAN;
    const float r = 10000.0f * mv / (rail_mv - mv);
    const float inv = 1.0f / 298.15f + logf(r / 10000.0f) / 3435.0f;
    return 1.0f / inv - 273.15f;
}

// HOW MUCH A RUN MAY DRAW, AT THIS TEMPERATURE.
//
// 4.75 A, not 5. The product promises 5 A, and the switch's own limit can be as low as 5.07 A; its
// current monitor is good to a few percent, so aiming at 4.75 keeps a run that reads high still under
// the trip. Full up to 85 C on the board, because the switch's 5 A is specified at 85 C AMBIENT and
// the board is never cooler than the air around it -- so a board at 85 C is in air no hotter than
// that. Past it the air may be hotter than the rating and nothing here can tell, so it falls away,
// to 1 A at 110 C. It never goes to dark for heat: a strip that goes out reads as broken, 1 A is
// three hundredths of a watt in the switch, and the switch's own thermal shutdown is still under it.
// A thermistor that cannot be read counts as 85 C: the edge of the rating, not the middle of it.
constexpr float MOST_A = 4.75f;
constexpr float HOT_FROM_C = 85.0f, HOT_TO_C = 110.0f, HOT_MOST_A = 1.0f;

static inline float most_amps(float board_c)
{
    if (board_c != board_c) board_c = HOT_FROM_C;   // NaN: unreadable
    if (board_c <= HOT_FROM_C) return MOST_A;
    if (board_c >= HOT_TO_C) return HOT_MOST_A;
    return MOST_A - (board_c - HOT_FROM_C) / (HOT_TO_C - HOT_FROM_C) * (MOST_A - HOT_MOST_A);
}

// ---------------------------------------------------------------- the prediction

// WHAT A FRAME WILL DRAW, BEFORE IT IS SENT. A strip's current is very nearly what its chips draw
// dark plus what each lit channel draws, in proportion to its byte. Both numbers are the strip's,
// not the board's, so both start as a cautious guess and are learned from the current monitor:
//
//   `per_unit`  amps for one channel at 255. 20 mA is a WS2812B at 5 V and about what every common
//               part draws per channel whatever its supply, because a 12 V or 24 V part puts its
//               LEDs in series rather than drawing more; it is learned UP at once and DOWN slowly,
//               because a strip that draws more than was thought is the one that trips.
//   `idle`      amps for the whole run showing black. A WS2812B is about a milliamp dark, which at a
//               thousand lights is an amp nobody sees. Learned whenever the run is lit and black.
struct Limiter
{
    float per_unit = 0.020f;
    float idle = -1.0f;      // negative: not yet measured, so a milliamp a light is assumed

    float idle_for(int lights) const { return idle >= 0 ? idle : 0.001f * (lights > 0 ? lights : 0); }

    // The scale, out of 256, that keeps a picture whose load (pixels.h) is `load` under `most` amps.
    uint16_t scale(uint32_t load, int lights, float most) const
    {
        if (load == 0) return 256;
        const float room = most - idle_for(lights);
        if (room <= 0) return 0;
        const float want = per_unit * (load / 255.0f);
        if (want <= room) return 256;
        const int s = (int)(256.0f * room / want);
        return (uint16_t)(s < 0 ? 0 : s > 256 ? 256 : s);
    }

    // A reading of `amps` while a frame whose load was `sent` had been showing long enough to settle.
    void heard(float amps, uint32_t sent, int lights)
    {
        if (sent == 0) {
            idle = idle < 0 ? amps : idle + (amps - idle) * 0.25f;
            return;
        }
        // Too little light to learn from: a few channels' worth is inside the monitor's own noise.
        const float units = sent / 255.0f;
        if (units < 8.0f) return;
        const float lit = amps - idle_for(lights);
        if (lit < 0.1f) return;
        const float k = lit / units;
        if (k > per_unit) per_unit = k;
        else per_unit += (k - per_unit) * 0.1f;
        if (per_unit < 0.002f) per_unit = 0.002f;
        if (per_unit > 0.080f) per_unit = 0.080f;
    }
};

// ---------------------------------------------------------------- the fault lines

// AN ACTIVE-LOW LINE, WATCHED OVER TIME. Both of a run's fault lines mean something only when they
// say it for a while or say it often: the switch's line goes low for a trip and comes back on its
// own 650 ms later, and the data-line protector's goes low for anything above ~6 V and clears ~2 ms
// after it has gone -- which a two-meter lead beside a strip at full white may briefly do.
struct Line
{
    bool on = false;
    uint32_t since = 0;
    uint16_t times = 0;

    // True on the reading where it goes low.
    bool see(bool asserted, uint32_t now)
    {
        if (asserted == on) return false;
        on = asserted;
        since = now;
        if (asserted) times++;
        return asserted;
    }
    uint32_t held(uint32_t now) const { return on ? now - since : 0; }
};

// FIVE TRIPS IN A MINUTE, OR ONE THAT LASTS FIVE SECONDS, AND THE RUN STAYS OFF until the board is next
// powered on. Retrying for ever is the switch's way of coping with a moment; a run that keeps tripping
// is a short in a cable or a strip that is not what the board was told, and cycling its power every
// 650 ms all night is heat and wear for nothing. A miswired data line is held off after 100 ms: the
// usual cause is the run's OWN V+ landing on DATA, so switching the run off is what takes the volts
// off the line.
constexpr int TRIPS_MOST = 5;
constexpr uint32_t TRIPS_WITHIN_MS = 60000, TRIP_LONGEST_MS = 5000, WIRING_LONGEST_MS = 100;

struct Faults
{
    Line sw, wires;
    uint8_t recent = 0;
    uint32_t first = 0;

    // From every pass, with the two lines as read (true = asserted). `lit` is whether the run is
    // switched on: a switch that is off has nothing to say. Returns the reason to hold the run off, or
    // FREE.
    uint8_t see(bool flt, bool dflt, bool lit, uint32_t now)
    {
        uint8_t why = FREE;
        if (sw.see(lit && flt, now)) {
            if (recent == 0 || now - first > TRIPS_WITHIN_MS) { recent = 0; first = now; }
            if (++recent >= TRIPS_MOST) why = TRIPS;
        }
        if (sw.held(now) >= TRIP_LONGEST_MS) why = TRIPS;
        wires.see(dflt, now);
        if (wires.held(now) >= WIRING_LONGEST_MS) why = WIRING;
        return why;
    }
};

// ---------------------------------------------------------------- the board, from app_main

// Before anything can light: the runs held off, the supply measured, each run's decision taken, and
// the runs that may light switched on and given time to power up. `nvs` is the strip's own namespace,
// where what each run was first lit on is kept beside everything else forgetting erases.
void begin(uint32_t nvs);

// May output `i` be sent a frame at all: its run is switched on and has had time to come up. An output
// whose run is off is sent nothing, so a dark strip's data input is never driven from a powered board.
bool live(int i);

// The scale, out of 256, to send output `i`'s picture at. Remembers what was sent, which is what the
// measurement afterwards is compared with.
uint16_t scale(int i, const px::Pixels &p);

// From the housekeeping loop, every pass, holding the strip: reads the lines and the monitors and
// decides. True when the pictures should be sent again -- a run has just come on, or what is showing
// now has to be dimmer than it was sent.
bool tick(uint32_t now);

// `power`, as JSON, when there is something new to say or it has been a while; false when not. `now`
// true says it regardless, for a broker that has just been reached.
bool report(char *out, size_t n, uint32_t now_ms, bool now);

}  // namespace guard
