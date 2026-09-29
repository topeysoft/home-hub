// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Which of two versions is newer, in the order the hub and the puck already use.
//
// "0.4.1-d384085" is a working-tree build of 0.4.1 (tools/dev.sh strip): it sorts after the release
// before it and before its own, so a strip that ran test builds still takes the real release. Anything
// that is not three numbers reads as 0.0.0, older than every real version, so a malformed offer is
// refused rather than taken. The same rule as brilliant/esp32-bridge/src/fwupdate.cpp and
// brain/hub/bridge.py `_older`; three places, one order.
//
// Free of ESP-IDF on purpose, so test_versions_native.cpp can hold it to that.
#pragma once

#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

struct Version { unsigned a, b, c; bool tagged; unsigned long n; };

inline Version version_of(const char *v) {
    Version r = {0, 0, 0, false, 0};
    int used = 0;
    if (!v || sscanf(v, "%u.%u.%u%n", &r.a, &r.b, &r.c, &used) != 3) return {0, 0, 0, false, 0};
    if (v[used] == '-') {
        r.tagged = true;
        const char *p = v + used + 1;
        while (*p && !isdigit((unsigned char)*p)) p++;
        r.n = strtoul(p, nullptr, 10);
    }
    return r;
}

// -1, 0 or 1, like strcmp.
inline int version_cmp(const char *x, const char *y) {
    const Version a = version_of(x), b = version_of(y);
    if (a.a != b.a) return a.a < b.a ? -1 : 1;
    if (a.b != b.b) return a.b < b.b ? -1 : 1;
    if (a.c != b.c) return a.c < b.c ? -1 : 1;
    if (a.tagged != b.tagged) return a.tagged ? -1 : 1;      // the release beats its own builds
    if (a.n != b.n) return a.n < b.n ? -1 : 1;
    return 0;
}
