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

// A Brilliant switch we can hear, and whose side it is on. Which of the two
// service numbers it advertises says everything, and it is the difference
// between "press this" and "you will have to start it over":
//
//   0x1827 Mesh Provisioning   nobody owns it. A switch out of a box is already
//                              here -- NO RESET, no ritual, it is simply ready.
//   0x1828 Mesh Proxy          it is on a network, and the Network ID in the
//                              advertisement says whose. Ours, or somebody
//                              else's -- and only the latter needs a reset.
//
// Drawn from the same advertisement tools/census.py has always classified on.
struct Nearby {
    enum State : uint8_t { Unclaimed, Ours, Foreign };
    NimBLEAddress addr;
    uint8_t uuid[16];       // Device UUID -- meaningful when Unclaimed
    uint8_t netid[8];       // whose network -- meaningful when claimed
    int rssi;
    State state = Unclaimed;
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
size_t pb_gatt_find_all(uint32_t ms, Nearby *out, size_t max);

// Everything heard, claimed or not, strongest first. This is what lets the house
// tell "nothing is out there" from "something is, but it is spoken for" -- two
// situations that look identical to a scan for claimable switches and want
// opposite things said to a person. `our_netid` is k3(netkey), eight bytes.
size_t pb_gatt_survey(uint32_t ms, const uint8_t our_netid[8], Nearby *out, size_t max);

// One switch, by the Device UUID in the QR's first sixteen bytes. This is what
// makes "the code you scanned" mean the switch in front of you rather than
// whichever unclaimed one is loudest.
Nearby pb_gatt_find(uint32_t ms, const uint8_t *want_uuid = nullptr);

// Ask a candidate to make itself known to a person, and say nothing else to it.
// Connect, send an Invite carrying an attention timer, hold the link while it
// runs, disconnect. The switch drops back to advertising unclaimed on its own,
// so a candidate that turns out to be the wrong one is left exactly as it was.
//
// It costs a second connection -- blink, ask, then provision the one they picked
// -- which is the price of a question that cannot otherwise be asked.
bool pb_gatt_blink(const Nearby &who, uint8_t seconds);

// Run the whole handshake against `who`. Returns true only on Complete, with
// the device key and element count left in `p`. Every other outcome -- refused
// connection, missing characteristics, a device that cannot prove it holds the
// code, silence -- returns false, and `p.state()`/`p.reason()` say which.
bool pb_gatt_provision(const Nearby &who, Provisioner &p, uint32_t timeout_ms = 40000);
