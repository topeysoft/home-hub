// PB-GATT: the bearer that carries a provisioning handshake to a switch.
//
// `Provisioner` knows the conversation and nothing about radios. This is the
// other half: find a switch that is advertising itself as unclaimed, open its
// provisioning service, and pump PDUs between the two until one of them is
// finished. It is the same shape as the proxy link in main.cpp -- same SAR, one
// service number along -- and deliberately kept beside it rather than folded in,
// because a puck spends almost all of its life bridging and only seconds of it
// claiming anything.
//
// IT BLOCKS, AND THAT IS A CHOICE. Provisioning takes tens of seconds and the
// bridge's loop is cooperative, so a puck doing this is not bridging. The
// alternative -- another state machine interleaved with the proxy's -- buys
// nothing for a job that happens when somebody is standing in a hallway holding
// a switch, waiting. The caller drops the proxy link first and picks it up after.
#pragma once
#include <Arduino.h>
#include <NimBLEDevice.h>
#include "provisioner.h"

// A switch in a box, advertising Mesh Provisioning (0x1827).
struct Unclaimed {
    NimBLEAddress addr;
    uint8_t uuid[16];       // its Device UUID, from the service data
    int rssi;
    bool found = false;
};

// Every unclaimed switch heard in the window, strongest first, and how many were
// written. EVERY one, not the loudest: taking the loudest is only safe when there
// is provably one, and in a house where somebody is redoing a room there is not.
// A codeless add has to offer them in turn, so it needs the whole list.
//
// Collects across the whole window rather than taking the first or the latest:
// these switches interleave a 0xFEE4 DFU beacon with the 0x1827 one, so a scan
// that keeps only the most recent advertisement misses them about half the time.
size_t pb_gatt_find_all(uint32_t ms, Unclaimed *out, size_t max);

// One switch, by the Device UUID in the QR's first sixteen bytes. This is what
// makes "the code you scanned" mean the switch in front of you rather than
// whichever unclaimed one is loudest.
Unclaimed pb_gatt_find(uint32_t ms, const uint8_t *want_uuid = nullptr);

// Ask a candidate to make itself known to a person, and say nothing else to it.
// Connect, send an Invite carrying an attention timer, hold the link while it
// runs, disconnect. The switch drops back to advertising unclaimed on its own,
// so a candidate that turns out to be the wrong one is left exactly as it was.
//
// It costs a second connection -- blink, ask, then provision the one they picked
// -- which is the price of a question that cannot otherwise be asked.
bool pb_gatt_blink(const Unclaimed &who, uint8_t seconds);

// Run the whole handshake against `who`. Returns true only on Complete, with
// the device key and element count left in `p`. Every other outcome -- refused
// connection, missing characteristics, a device that cannot prove it holds the
// code, silence -- returns false, and `p.state()`/`p.reason()` say which.
bool pb_gatt_provision(const Unclaimed &who, Provisioner &p, uint32_t timeout_ms = 40000);
