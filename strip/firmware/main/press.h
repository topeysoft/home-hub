// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The one button, read: a short press lets the hub in, a long hold forgets the house.
//
// It was a handful of lines in the housekeeping loop, and it is here now for one reason: rev A's
// button is sealed into the wall of a box that lives outdoors, where the thing pressing it may be a
// shrinking seal on a cold night or ice, and the three rules that make that harmless deserve a test
// rather than a reading:
//
//   NOTHING COUNTS UNTIL THE BUTTON HAS BEEN SEEN LET GO. A button held at boot -- by a finger, by
//   ice, by a devkit whose BOOT pin sits low -- is ignored until it is released. Without this a
//   board that boots with it held factory-resets itself five seconds into every boot, for ever.
//   A PRESS IS COUNTED ON THE WAY UP, and only if the hold never armed, so the two lengths of the same
//   button cannot be confused: under a second lets somebody in, five forgets the house, and the one
//   second between turns the strip red to say which is coming.
//   AND A PRESS SHORTER THAN `shortest` IS A CONTACT BOUNCING, not a finger. Zero on the devkit,
//   where it always was zero; rev A sets its own (board.h).
//
// Free of ESP-IDF, so test_press_native.cpp can hold it to all three.
#pragma once

#include <stdint.h>

struct Press
{
    uint32_t armed_after = 1000, done_after = 5000, shortest = 0;

    // What happened on one reading. More than one can, in principle, on a reading that comes late.
    enum : uint8_t { DOWN = 1, ARMED = 2, DONE = 4, PRESSED = 8, LET_GO = 16 };

    bool released = false, armed = false, down = false;
    uint32_t down_at = 0;

    // `up` is the pin as read: high is not pressed.
    uint8_t tick(bool up, uint32_t now)
    {
        uint8_t ev = 0;
        if (up) {
            released = true;
            if (down) {
                const uint32_t held = now - down_at;
                down = false;
                if (armed) { armed = false; ev |= LET_GO; }
                else if (held < armed_after && held >= shortest) ev |= PRESSED;
            }
        } else if (released) {
            if (!down) { down = true; down_at = now; ev |= DOWN; }
            const uint32_t held = now - down_at;
            if (!armed && held > armed_after) { armed = true; ev |= ARMED; }
            if (held > done_after) ev |= DONE;
        }
        return ev;
    }
};
