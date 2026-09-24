// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// main/versions.h on the Mac.
//
//     c++ -std=c++17 -O1 -o /tmp/versions test_versions_native.cpp && /tmp/versions
//
// (The -isysroot note in test_hub_uri_native.cpp applies here too.)
//
// This exists because the order is a promise across three codebases -- the puck, the strip and the
// brain -- and the strip is the one that would otherwise refuse the release it was developing.
#include "main/versions.h"

static int failures = 0;

static void is(const char *a, const char *b, int want) {
    const int got = version_cmp(a, b);
    if (got != want) { printf("FAIL %s vs %s: %d, wanted %d\n", a, b, got, want); failures++; }
}

int main() {
    is("0.4.0", "0.4.1", -1);
    is("0.10.0", "0.9.0", 1);                  // numbers, not words
    is("0.4.1-d384085", "0.4.1", -1);          // a test build comes before its release...
    is("0.4.0", "0.4.1-d384085", -1);          // ...and after the one before
    is("0.4.1-d5", "0.4.1-d6", -1);
    is("0.4.1", "0.4.1", 0);
    is("tuesday", "0.0.1", -1);                // not a version: older than everything, so refused
    is("", "0.0.0", 0);
    printf(failures ? "%d failed\n" : "ok\n", failures);
    return failures ? 1 : 0;
}
