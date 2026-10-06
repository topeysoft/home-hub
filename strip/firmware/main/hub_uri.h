// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Where the broker is, from whatever the hub said it was.
//
// The hub hands a strip `mhost` during setup, and brain/hub/strip.py sends the hub's NAME when it has
// one and its ADDRESS when it does not. The first version of this appended ".local" to either, so a
// house whose broker is known by address adopted strips that finished setup, joined the Wi-Fi, looked
// for mqtt://192.168.86.53.local:1883 -- which is nowhere -- and said "nobody came". A strip that is
// set up and never appears, found by adopting one through a bridge puck (docs/strip.md item 39).
//
// So: a bare name is an mDNS name and gets ".local"; anything with a dot in it is already somewhere
// (an address, or a name that says its own domain) and is used as given; an IPv6 address is bracketed
// the way a URI needs. Free of ESP-IDF on purpose, so test_hub_uri_native.cpp can hold it to that.
#pragma once

#include <string>

inline std::string broker_host(const std::string &given) {
    if (given.empty()) return "";
    if (given.find(':') != std::string::npos) return "[" + given + "]";
    if (given.find('.') != std::string::npos) return given;
    return given + ".local";
}

inline std::string broker_uri(const std::string &given, int port = 1883) {
    const std::string host = broker_host(given);
    return host.empty() ? "" : "mqtt://" + host + ":" + std::to_string(port);
}
