#include "claim.h"
#include "pb_gatt.h"
#include "provisioner.h"
#include "mesh_crypto.h"

static const uint8_t *g_netkey = nullptr;
static uint32_t g_iv = 0;
static void (*g_publish)(const char *, const char *) = nullptr;

static char g_cmd[160];
static volatile bool g_pending = false;
static volatile bool g_running = false;

// The candidates from the last survey. `blink` and `add` name a switch by its
// Device UUID, which is what the QR carries and what an advertisement gives, and
// both need the BLE address that went with it -- so a survey is a prerequisite
// rather than a convenience, and saying so is better than silently re-scanning
// and blinking a different switch than the one the person was shown.
static Nearby g_seen[12];
static size_t g_count = 0;

void claim_begin(const uint8_t netkey[16], uint32_t iv_index,
                 void (*publish)(const char *, const char *)) {
    g_netkey = netkey;
    g_iv = iv_index;
    g_publish = publish;
}

bool claim_queue(const char *payload, size_t len) {
    if (g_pending || g_running) return false;
    if (len >= sizeof(g_cmd)) return false;
    memcpy(g_cmd, payload, len);
    g_cmd[len] = 0;
    g_pending = true;
    return true;
}

bool claim_busy() { return g_pending || g_running; }

static void say(const char *leaf, const char *payload) {
    if (g_publish) g_publish(leaf, payload);
}

static bool unhex(const char *h, uint8_t *out, size_t n) {
    for (size_t i = 0; i < n; i++) {
        char b[3] = {h[i * 2], h[i * 2 + 1], 0};
        if (!isxdigit((int)b[0]) || !isxdigit((int)b[1])) return false;
        out[i] = (uint8_t)strtol(b, nullptr, 16);
    }
    return true;
}

static Nearby *by_uuid(const char *hex) {
    uint8_t want[16];
    if (strlen(hex) < 32 || !unhex(hex, want, 16)) return nullptr;
    for (size_t i = 0; i < g_count; i++) {
        if (g_seen[i].state == Nearby::Unclaimed && !memcmp(g_seen[i].uuid, want, 16)) {
            return &g_seen[i];
        }
    }
    return nullptr;
}

static void do_survey() {
    uint8_t ournet[8];
    mesh_k3(g_netkey, ournet);
    g_count = pb_gatt_survey(6000, ournet, g_seen, 12);

    // Small enough to build in one buffer, and a switch list that needs streaming
    // is a house with problems this message cannot help with.
    char out[900];
    size_t o = snprintf(out, sizeof(out), "[");
    for (size_t i = 0; i < g_count && o < sizeof(out) - 120; i++) {
        const Nearby &s = g_seen[i];
        const char *st = s.state == Nearby::Unclaimed ? "unclaimed"
                       : (s.state == Nearby::Ours ? "ours" : "other");
        o += snprintf(out + o, sizeof(out) - o, "%s{\"state\":\"%s\",\"rssi\":%d,\"addr\":\"%s\"",
                      i ? "," : "", st, s.rssi, s.addr.toString().c_str());
        if (s.state == Nearby::Unclaimed) {
            o += snprintf(out + o, sizeof(out) - o, ",\"uuid\":\"");
            for (int k = 0; k < 16 && o < sizeof(out) - 40; k++) {
                o += snprintf(out + o, sizeof(out) - o, "%02x", s.uuid[k]);
            }
            o += snprintf(out + o, sizeof(out) - o, "\"");
        } else {
            o += snprintf(out + o, sizeof(out) - o, ",\"net\":\"");
            for (int k = 0; k < 8 && o < sizeof(out) - 24; k++) {
                o += snprintf(out + o, sizeof(out) - o, "%02x", s.netid[k]);
            }
            o += snprintf(out + o, sizeof(out) - o, "\"");
        }
        o += snprintf(out + o, sizeof(out) - o, "}");
    }
    snprintf(out + o, sizeof(out) - o, "]");
    say("nearby", out);
    Serial.printf("[claim] survey: %u nearby\n", (unsigned)g_count);
}

static void do_blink(const char *uuid_hex, int seconds) {
    Nearby *who = by_uuid(uuid_hex);
    if (!who) { say("claimed", "{\"ok\":false,\"why\":\"not in the last survey\"}"); return; }
    const bool ok = pb_gatt_blink(*who, (uint8_t)constrain(seconds, 1, 30));
    say("claimed", ok ? "{\"ok\":true,\"what\":\"blink\"}"
                      : "{\"ok\":false,\"what\":\"blink\",\"why\":\"could not reach it\"}");
}

static void do_add(const char *uuid_hex, unsigned unicast, const char *oob_hex) {
    Nearby *who = by_uuid(uuid_hex);
    if (!who) { say("claimed", "{\"ok\":false,\"why\":\"not in the last survey\"}"); return; }
    if (!unicast || unicast >= 0x8000) {
        say("claimed", "{\"ok\":false,\"why\":\"the address to assign is not a unicast\"}");
        return;
    }

    Provisioner p;
    uint8_t oob[16];
    if (oob_hex && strlen(oob_hex) >= 32 && unhex(oob_hex, oob, 16)) {
        p.useStaticOOB(oob);               // the QR add: the switch must prove it holds this
    }
    // No attention here even on the codeless route: the blink that identified it
    // has already happened, and asking a switch to announce itself again while it
    // is being claimed would be a light show with nothing to say.
    p.begin(g_netkey, 0, 0, g_iv, (uint16_t)unicast);

    const bool ok = pb_gatt_provision(*who, p);
    char out[220];
    if (ok) {
        size_t o = snprintf(out, sizeof(out),
                            "{\"ok\":true,\"unicast\":\"%04x\",\"elements\":%u,\"devkey\":\"",
                            (unsigned)unicast, (unsigned)p.elements());
        for (int k = 0; k < 16; k++) o += snprintf(out + o, sizeof(out) - o, "%02x", p.devkey()[k]);
        snprintf(out + o, sizeof(out) - o, "\"}");
        // The device key is this node's alone and the hub needs it to configure
        // anything. It goes over the house's own broker, which already carries
        // the mesh's traffic, and never off the LAN.
    } else {
        const char *why = p.state() == Provisioner::FAILED
            ? (p.reason() == 0x05 ? "it could not prove it holds that code" : "it refused the exchange")
            : "it stopped answering";
        snprintf(out, sizeof(out), "{\"ok\":false,\"why\":\"%s\",\"state\":%u,\"reason\":%u}",
                 why, (unsigned)p.state(), (unsigned)p.reason());
    }
    say("claimed", out);
    Serial.printf("[claim] add %s -> %s\n", uuid_hex, ok ? "in" : "no");
    g_count = 0;                            // the survey is stale the moment one joins
}

void claim_tick() {
    if (!g_pending || !g_netkey) return;
    g_pending = false;
    g_running = true;

    char cmd[sizeof(g_cmd)];
    strlcpy(cmd, g_cmd, sizeof(cmd));
    char *verb = strtok(cmd, " ");
    if (!verb) { g_running = false; return; }

    if (!strcasecmp(verb, "survey")) {
        do_survey();
    } else if (!strcasecmp(verb, "blink")) {
        const char *uuid = strtok(nullptr, " ");
        const char *secs = strtok(nullptr, " ");
        if (uuid) do_blink(uuid, secs ? atoi(secs) : 5);
    } else if (!strcasecmp(verb, "add")) {
        const char *uuid = strtok(nullptr, " ");
        const char *addr = strtok(nullptr, " ");
        const char *oob = strtok(nullptr, " ");
        if (uuid && addr) do_add(uuid, strtoul(addr, nullptr, 16), oob);
    } else {
        say("claimed", "{\"ok\":false,\"why\":\"unknown command\"}");
    }
    g_running = false;
}
