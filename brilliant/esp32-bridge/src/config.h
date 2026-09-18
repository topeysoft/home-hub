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
//   set mqtt <host> <port> <user> <pass>  -> ok mqtt
//   set keys <netkey> <appkey> <iv>    -> ok keys      (32 hex, 32 hex, decimal)
//   set base <base>                    -> ok base      (MQTT base, default "mesh")
//   set label <label>                  -> ok label     (the maker's word, "Brilliant")
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

#define BRIDGE_FW "0.3.0"

struct BridgeConfig {
    char ssid[33];
    char pass[65];
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
};

extern BridgeConfig cfg;

// NVS first, the compiled header second, blank third. Call before anything reads cfg.
void configLoad();
// Nothing to connect to: no Wi-Fi at all. The puck waits on the cable (and blinks amber).
bool configBlank();
// The line protocol above, on its own task. `chip` is this puck's id for `hello`.
void configSerialBegin(const char *chip);

// One line about how the bridge is doing right now, for `status`. Lives in
// main.cpp, which is where the state is.
void bridgeStatusLine(char *out, size_t n);
