#include "config.h"

#include <Preferences.h>
#include <string.h>

// The compiled fallback. Optional: a shipped image is built with no secrets
// header at all and comes up blank, which is the whole point of this file.
#ifndef SECRETS_FILE
#define SECRETS_FILE "secrets.h"
#endif
#if __has_include(SECRETS_FILE)
#include SECRETS_FILE
#define HAVE_SECRETS 1
// Headers written before a field existed leave it out; the fallback's fallback.
#ifndef MQTT_USER
#define MQTT_USER ""
#endif
#ifndef MQTT_PASS
#define MQTT_PASS ""
#endif
#ifndef MQTT_BASE
#define MQTT_BASE "mesh"
#endif
#ifndef DEVICE_LABEL
#define DEVICE_LABEL "Brilliant"
#endif
#endif

BridgeConfig cfg;

static Preferences store;        // its own namespace; the bridge's runtime counters live in "meshbridge"
static const char *NS = "bridgecfg";
static char chipId[8] = "000000";

// ---------------------------------------------------------------- loading

static void str(char *dst, size_t n, const char *key, const char *fallback) {
    String v = store.getString(key, fallback ? fallback : "");
    strlcpy(dst, v.c_str(), n);
}

void configLoad() {
    memset(&cfg, 0, sizeof(cfg));
    store.begin(NS, true);
    // Everything below reads NVS with the compiled value as the default, so a
    // puck with nothing written keeps behaving exactly as its header says.
#ifdef HAVE_SECRETS
    str(cfg.ssid, sizeof(cfg.ssid), "ssid", WIFI_SSID);
    str(cfg.pass, sizeof(cfg.pass), "pass", WIFI_PASS);
    str(cfg.mqttHost, sizeof(cfg.mqttHost), "mhost", MQTT_HOST);
    cfg.mqttPort = store.getUShort("mport", MQTT_PORT);
    str(cfg.mqttUser, sizeof(cfg.mqttUser), "muser", MQTT_USER);
    str(cfg.mqttPass, sizeof(cfg.mqttPass), "mpass", MQTT_PASS);
    str(cfg.mqttBase, sizeof(cfg.mqttBase), "mbase", MQTT_BASE);
    str(cfg.label, sizeof(cfg.label), "label", DEVICE_LABEL);
    if (store.getBytes("netkey", cfg.netKey, 16) == 16 && store.getBytes("appkey", cfg.appKey, 16) == 16) {
        cfg.ivIndex = store.getUInt("iv", 0);
    } else {
        memcpy(cfg.netKey, NET_KEY, 16);
        memcpy(cfg.appKey, APP_KEY, 16);
        cfg.ivIndex = IV_INDEX;
    }
    cfg.haveKeys = true;
#else
    str(cfg.ssid, sizeof(cfg.ssid), "ssid", "");
    str(cfg.pass, sizeof(cfg.pass), "pass", "");
    str(cfg.mqttHost, sizeof(cfg.mqttHost), "mhost", "");
    cfg.mqttPort = store.getUShort("mport", 1883);
    str(cfg.mqttUser, sizeof(cfg.mqttUser), "muser", "");
    str(cfg.mqttPass, sizeof(cfg.mqttPass), "mpass", "");
    str(cfg.mqttBase, sizeof(cfg.mqttBase), "mbase", "mesh");
    str(cfg.label, sizeof(cfg.label), "label", "Brilliant");
    cfg.haveKeys = store.getBytes("netkey", cfg.netKey, 16) == 16 && store.getBytes("appkey", cfg.appKey, 16) == 16;
    cfg.ivIndex = store.getUInt("iv", 0);
#endif
    store.end();
    if (!cfg.mqttBase[0]) strlcpy(cfg.mqttBase, "mesh", sizeof(cfg.mqttBase));
    if (!cfg.label[0]) strlcpy(cfg.label, "Brilliant", sizeof(cfg.label));
}

bool configBlank() { return cfg.ssid[0] == 0; }

// ---------------------------------------------------------------- the line protocol

static int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

// hex text -> bytes; returns the byte count, or -1 for anything that is not hex
static int unhex(const char *s, uint8_t *out, size_t max) {
    size_t n = strlen(s);
    if (n & 1) return -1;
    if (n / 2 > max) return -1;
    for (size_t i = 0; i < n; i += 2) {
        int a = hexval(s[i]), b = hexval(s[i + 1]);
        if (a < 0 || b < 0) return -1;
        out[i / 2] = (uint8_t)((a << 4) | b);
    }
    return (int)(n / 2);
}

// a hex-encoded string argument into a C string; false if it is not hex or does not fit
static bool unhexStr(const char *s, char *out, size_t max) {
    uint8_t buf[128];
    int n = unhex(s, buf, sizeof(buf));
    if (n < 0 || (size_t)n >= max) return false;
    memcpy(out, buf, n);
    out[n] = 0;
    return true;
}

// Which port the hub is on. An S3 devkit has two: the native USB one (HWCDC, `Serial` when the
// build says CDC-on-boot) and the UART one behind a bridge chip (`Serial0`). The hub's cable can
// land on either -- and on the boards we have, only the UART side powers the LED -- so the task
// listens on both and answers on whichever one asked. A classic ESP32 has one port, and there the
// two names are the same object.
static Stream *asked = &Serial;
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
#define SECOND_PORT Serial0          // the UART-side port next to the native one
#endif

// An answer to the hub is sent in pieces no bigger than the CDC's hardware FIFO, with a flush
// between. The S3's hardware-CDC driver in this core decides for itself whether a host is listening
// and, when it decides wrongly (it does, on a Mac that has reopened the port), a longer write comes
// out as its head and its tail with the middle dropped -- "bridge c8ebbat". Short pieces get through
// whole nearly always; the hub retries the rare one that does not (tools/puck_cable.py).
static void reply(const char *s) {
    char line[200];
    size_t n = (size_t)snprintf(line, sizeof(line), "%s\r\n", s);
    for (size_t at = 0; at < n; at += 60) {
        size_t k = n - at < 60 ? n - at : 60;
        asked->write((const uint8_t *)line + at, k);
        asked->flush();
        if (at + k < n) vTaskDelay(pdMS_TO_TICKS(5));
    }
}

// `line` is split in place. Up to six words is every command above.
static void handle(char *line) {
    char *w[7] = {0};
    int nw = 0;
    for (char *p = strtok(line, " \t"); p && nw < 7; p = strtok(nullptr, " \t")) w[nw++] = p;
    if (!nw) return;

    if (!strcmp(w[0], "hello")) {
        char out[64];
        snprintf(out, sizeof(out), "bridge %s %s %s", chipId, BRIDGE_FW, configBlank() ? "blank" : "set");
        return reply(out);
    }
    if (!strcmp(w[0], "status")) {
        char out[160];
        bridgeStatusLine(out, sizeof(out));
        return reply(out);
    }
    if (!strcmp(w[0], "apply")) {
        reply("ok apply");
        delay(100);
        ESP.restart();
    }
    if (!strcmp(w[0], "wipe")) {
        store.begin(NS, false);
        store.clear();
        store.end();
        reply("ok wipe");
        delay(100);
        ESP.restart();
    }
    if (strcmp(w[0], "set") || nw < 3) return reply("err what");

    char a[65], b[65], c[65];
    store.begin(NS, false);
    bool ok = false;
    if (!strcmp(w[1], "wifi") && nw == 4) {
        ok = unhexStr(w[2], a, 33) && unhexStr(w[3], b, 65) && a[0];
        if (ok) { store.putString("ssid", a); store.putString("pass", b); }
    } else if (!strcmp(w[1], "mqtt") && nw == 6) {
        long port = atol(w[3]);
        ok = unhexStr(w[2], a, 65) && port > 0 && port < 65536 && unhexStr(w[4], b, 33) && unhexStr(w[5], c, 65) && a[0];
        if (ok) { store.putString("mhost", a); store.putUShort("mport", (uint16_t)port); store.putString("muser", b); store.putString("mpass", c); }
    } else if (!strcmp(w[1], "keys") && nw == 5) {
        uint8_t nk[16], ak[16];
        ok = unhex(w[2], nk, 16) == 16 && unhex(w[3], ak, 16) == 16;
        if (ok) { store.putBytes("netkey", nk, 16); store.putBytes("appkey", ak, 16); store.putUInt("iv", (uint32_t)atol(w[4])); }
    } else if (!strcmp(w[1], "base") && nw == 3) {
        ok = unhexStr(w[2], a, 17) && a[0];
        if (ok) store.putString("mbase", a);
    } else if (!strcmp(w[1], "label") && nw == 3) {
        ok = unhexStr(w[2], a, 25) && a[0];
        if (ok) store.putString("label", a);
    } else {
        store.end();
        return reply("err what");
    }
    store.end();
    if (!ok) return reply("err bad");
    char out[24];
    snprintf(out, sizeof(out), "ok %s", w[1]);
    reply(out);
}

// one line buffer per port, so a half-typed line on one is not finished by the other
struct Port { Stream *io; char line[400]; size_t n; };
static void pump(Port &p) {
    while (p.io->available()) {
        char c = (char)p.io->read();
        if (c == '\n' || c == '\r') {
            if (p.n) { p.line[p.n] = 0; asked = p.io; handle(p.line); p.n = 0; }
        } else if (p.n < sizeof(p.line) - 1) {
            p.line[p.n++] = c;
        } else {
            p.n = 0;   // a line that long is not one of ours; start again
        }
    }
}

static void serialTask(void *) {
#ifdef SECOND_PORT
    static Port ports[] = {{&Serial, {0}, 0}, {&SECOND_PORT, {0}, 0}};
#else
    static Port ports[] = {{&Serial, {0}, 0}};   // a classic ESP32: one physical port, and Serial is it
#endif
    const int n = sizeof(ports) / sizeof(ports[0]);
    for (;;) {
        for (int i = 0; i < n; i++) pump(ports[i]);
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void configSerialBegin(const char *chip) {
    strlcpy(chipId, chip, sizeof(chipId));
#ifdef SECOND_PORT
    SECOND_PORT.begin(115200);
#endif
    // 8K, not 4: `status` formats an IP and a few strings, and a stack that is a little too small
    // does not panic, it quietly corrupts the reply. Found the hard way.
    xTaskCreate(serialTask, "cfg-serial", 8192, nullptr, 1, nullptr);
}
