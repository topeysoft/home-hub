// What a puck needs to know to be a bridge, and how it is told.
//
// Until now all of it was compiled in from include/secrets.h: the Wi-Fi, the
// broker, the mesh keys. That is fine for a puck on a developer's desk and
// useless for one in a bag, because the hub has nothing it can WRITE to
// without a rebuild. So the config now lives in NVS and the compiled header
// is only a fallback -- the two pucks that already work keep working, and a
// board flashed from a shipped image with no secrets at all boots "blank"
// and waits to be told.
//
// It is told over the USB serial line by the hub (design/puck/Cable.dc.html:
// plug it into the hub once, the hub writes everything). Lines in, lines out,
// 115200 baud, nothing binary:
//
//   hello                              -> bridge <chip> <fw> blank|set
//   set wifi <ssid> <pass>             -> ok wifi
//   set wifi2 <ssid> <pass>            -> ok wifi2     the OTHER key on the ring; see below
//   set name <hostname>                -> ok name      the hub's name, resolved before any number
//   set mqtt <host> <port> <user> <pass>  -> ok mqtt
//   set keys <netkey> <appkey> <iv>    -> ok keys      (32 hex, 32 hex, decimal)
//   set base <base>                    -> ok base      (MQTT base, default "mesh")
//   set label <label>                  -> ok label     (the maker's word, "Brilliant")
//   set night <0|1> <0-255>            -> ok night     the nightlight, and how bright
//   set settled <0|1>                  -> ok settled   it has been placed; the instrument retires
//   status                             -> status wifi=<ip|down> mqtt=up|down proxy=<desc> switches=<n>
//   apply                              -> ok apply, then the puck restarts on the new config
//   wipe                               -> ok wipe, then it restarts blank
//
// Every free-text argument (ssid, pass, host, user, base, label) is sent HEX
// ENCODED, so a password with a space or a quote in it needs no quoting rules
// on either side. Keys are hex already. Anything the puck did not understand
// answers `err <why>`; the hub's log lines that start with `[` are noise to
// the protocol and the hub ignores them.
//
// The line reader runs on its own task, because the main loop stalls for up
// to two seconds while it hunts for a proxy and a hub writing config must not
// wait on that.
#pragma once

#include <Arduino.h>

#define BRIDGE_FW "0.6.0"   // the first that can take the next one over the air (src/fwupdate.h)

// TWO KEYS ON THE RING, AND A NAME RATHER THAN A NUMBER (docs/network.md, pieces 1 and 3).
//
// A puck used to hold one Wi-Fi and one broker address, both written once over a cable. Both went
// stale the day the house changed anything: a new router password made the puck deaf for ever, and
// a DHCP reshuffle did the same without anybody touching the Wi-Fi at all. Neither had a way back
// that was not a walk around the house with a USB lead.
//
// So the puck now holds the credentials it is using AND the ones it used before, and when it can
// reach neither it alternates between them every couple of minutes, for ever. That one change makes
// the order of a move stop mattering -- whoever arrives second finds the other already there -- and
// makes a mistyped password repair itself within minutes instead of stranding the house.
//
// The broker is found by name first (mDNS), then by the last address that actually answered, then
// by the address it was given. Any success is remembered. A house whose router filters multicast is
// caught by the second; a house that reshuffles its leases is caught by the first.

struct BridgeConfig {
    char ssid[33];
    char pass[65];
    char ssid2[33];     // the other key on the ring; empty until the house has moved once
    char pass2[65];
    char mqttName[33];  // the hub's name ("hub"), resolved over mDNS before mqttHost is tried
    char lastIp[16];    // the last address that actually answered, whatever it was found by
    uint32_t cfgAt;     // the newest cfg command already applied: a retained one must not replay
    char mqttHost[65];
    uint16_t mqttPort;
    char mqttUser[33];
    char mqttPass[65];
    char mqttBase[17];
    char label[25];
    uint8_t netKey[16];
    uint8_t appKey[16];
    uint32_t ivIndex;
    bool haveKeys;      // false on a blank puck: it can join Wi-Fi but has no mesh to speak

    // WHAT THE LIGHT DOES ONCE IT HAS FINISHED BEING AN INSTRUMENT (docs/puck-light.md).
    //
    // `settled` is set when the household taps "Leave it here" (POST /bridge/placed), and it is an
    // EVENT rather than a timer on purpose: a puck that has never been told it is home is still
    // being carried around, and must keep its green. `night` and `nightLevel` are the answer to the
    // one question the sheet asks at that moment. Both live here rather than in light.cpp because
    // they have to survive a reboot with the hub down -- a nightlight that goes out in a power cut
    // and needs the broker back before it returns is not a nightlight.
    //
    // Neither of these can make the light lie: lightRefresh() puts a fault above both of them.
    bool settled;
    bool night;         // off by default. Nobody gets a glowing object they did not ask for
    uint8_t nightLevel; // 0-255, scaling WARM in light.cpp
};

extern BridgeConfig cfg;

// NVS first, the compiled header second, blank third. Call before anything reads cfg.
void configLoad();
// Nothing to connect to: no Wi-Fi at all. The puck waits on the cable (and blinks amber).
bool configBlank();
// The line protocol above, on its own task. `chip` is this puck's id for `hello`.
void configSerialBegin(const char *chip);

// ---- what the running bridge writes back ----

// An address that answered. Cheap to call: it writes only when the value actually changed, because
// NVS has a finite number of erases in it and a broker reconnect loop is not a rare event.
void configRemember(const char *ip);

// A new Wi-Fi arrived over the air. The one in use becomes the spare, the new one takes its place,
// and `at` is remembered so the retained command that carried it is not applied a second time.
// Returns false if this command has already been applied, or is not usable.
bool configNewWifi(const char *ssid, const char *pass, const char *name, const char *ip, uint32_t at);

// Everybody made it: the spare is no longer worth keeping. Only the hub may decide this -- a puck
// that is online cannot tell whether the hub can see it.
void configForgetSpare(uint32_t at);

// One of the two actually worked. If that was the spare (configSwapWifi put it in front), write the
// ring down in its new order, so a puck that reboots does not spend two minutes on the dead one
// first. Does nothing when the order on disk is already right.
void configConfirmWifi();

// The household's answer about the light, and the moment it was placed. Written through to NVS and
// to `cfg` at once, so the light responds now and still knows after a power cut. Like configRemember
// these write only when the value actually changed: NVS has a finite number of erases in it, and a
// brightness slider dragged across a room is not a rare event.
void configSetNight(bool on, uint8_t level);
void configSetSettled(bool settled);

// Swap the two keys on the ring, in memory only. Called when neither network can be reached, so the
// next attempt tries the other one; nothing is written until one of them actually works.
void configSwapWifi();

// One line about how the bridge is doing right now, for `status`. Lives in
// main.cpp, which is where the state is.
void bridgeStatusLine(char *out, size_t n);
