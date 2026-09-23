// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// main/hub_uri.h on the Mac.
//
//     c++ -std=c++17 -O1 -o /tmp/uri test_hub_uri_native.cpp && /tmp/uri
//
// (On a Mac whose Command Line Tools cannot link against their own newest SDK, add
// -isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk -- docs/strip.md item 41.)
//
// This exists because a strip that cannot find the broker LOOKS SET UP. It joins the Wi-Fi, the wall
// says it is in, and it never appears -- and the address it was looking for is only in its own log.
#include "main/hub_uri.h"

#include <stdio.h>

static int failures = 0;

static void is(const std::string &given, const std::string &want) {
    const std::string got = broker_uri(given);
    if (got != want) {
        printf("  FAIL: \"%s\" -> \"%s\", wanted \"%s\"\n", given.c_str(), got.c_str(), want.c_str());
        failures++;
    }
}

int main() {
    is("hub", "mqtt://hub.local:1883");                    // the hub's own name, the usual case
    is("192.168.86.53", "mqtt://192.168.86.53:1883");      // THE BUG: an address is not a name
    is("hub.local", "mqtt://hub.local:1883");              // a name that already says .local
    is("hub.lan", "mqtt://hub.lan:1883");                  // a router's own domain
    is("fd85::1", "mqtt://[fd85::1]:1883");                // IPv6 wants brackets in a URI
    is("", "");                                            // no hub: somebody else's light
    printf(failures ? "%d FAILED\n" : "hub_uri: all good\n", failures);
    return failures ? 1 : 0;
}
