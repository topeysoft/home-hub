#include "recorder.h"
#include "mesh_crypto.h"

// ---- state captured at provisioning ----
static uint8_t  g_netkey[16], g_devkey[16], g_appkey[16];
static bool     g_haveAppkey = false;
static uint16_t g_unicast    = 0;      // our address
static uint16_t g_prov       = 0;      // the app/provisioner's address (learned)
static uint32_t g_iv         = 0;
static uint32_t g_txseq      = 0;      // our outbound sequence
static void (*g_send)(uint8_t, const uint8_t *, size_t) = nullptr;

// ---- inbound lower-transport reassembly (one context at a time is enough) ----
static uint16_t rx_seqzero = 0xFFFF;
static uint8_t  rx_buf[256];
static uint32_t rx_mask = 0;
static uint8_t  rx_segn = 0;
static size_t   rx_total = 0;
static uint32_t rx_seq0 = 0;
static uint8_t  rx_szmic = 0;

bool rec_have_appkey() { return g_haveAppkey; }

void rec_init(const uint8_t netkey[16], const uint8_t devkey[16],
              uint16_t unicast, uint32_t iv) {
    memcpy(g_netkey, netkey, 16);
    memcpy(g_devkey, devkey, 16);
    g_unicast = unicast; g_iv = iv; g_haveAppkey = false; g_txseq = 0;
    Serial.printf("[rec] armed: our unicast 0x%04x, iv index %u\n", unicast, iv);
}
void rec_set_sender(void (*s)(uint8_t, const uint8_t *, size_t)) { g_send = s; }

// ---- outbound: encrypt an access PDU and send it to the app ----
static void send_access(const uint8_t *access, size_t alen, bool useAppkey) {
    if (!g_send || g_prov == 0) return;
    uint8_t upper[64];
    uint32_t seq0 = g_txseq++;
    size_t ulen = mesh_app_encrypt(useAppkey ? g_appkey : g_devkey, !useAppkey,
                                   g_iv, seq0, g_unicast, g_prov,
                                   access, alen, upper);
    uint8_t akf_aid = useAppkey ? (0x40 | mesh_k4(g_appkey)) : 0x00;

    if (ulen <= 15) {
        uint8_t lower[16]; lower[0] = akf_aid; memcpy(lower + 1, upper, ulen);
        uint8_t npdu[48];
        size_t n = mesh_net_encrypt(g_netkey, g_iv, 0, 7, seq0, g_unicast,
                                    g_prov, lower, ulen + 1, 0x00, npdu);
        if (n) g_send(0x00, npdu, n);
        return;
    }
    // segmented: 12 bytes of upper transport per segment
    uint8_t segn = (ulen + 11) / 12 - 1;
    uint16_t seqzero = seq0 & 0x1FFF;
    for (uint8_t i = 0; i <= segn; i++) {
        size_t off = i * 12, c = (ulen - off < 12) ? (ulen - off) : 12;
        uint32_t hdr = ((uint32_t)seqzero << 10) | ((uint32_t)i << 5) | segn; // SZMIC 0
        uint8_t lower[16];
        lower[0] = 0x80 | akf_aid;
        lower[1] = (hdr >> 16) & 0xFF; lower[2] = (hdr >> 8) & 0xFF; lower[3] = hdr & 0xFF;
        memcpy(lower + 4, upper + off, c);
        uint32_t seq = (i == 0) ? seq0 : g_txseq++;
        uint8_t npdu[48];
        size_t n = mesh_net_encrypt(g_netkey, g_iv, 0, 7, seq, g_unicast,
                                    g_prov, lower, c + 4, 0x00, npdu);
        if (n) g_send(0x00, npdu, n);
        delay(20);
    }
}

// ---- acknowledge an inbound segmented message so the app stops resending ----
static void send_segack(uint16_t seqzero, uint32_t block) {
    if (!g_send) return;
    uint8_t t[7];
    t[0] = 0x00;
    uint16_t sz = (seqzero << 2) & 0x7FFF;
    t[1] = sz >> 8; t[2] = sz & 0xFF;
    t[3] = block >> 24; t[4] = block >> 16; t[5] = block >> 8; t[6] = block;
    uint32_t seq = g_txseq++;
    uint8_t npdu[48];
    size_t n = mesh_net_encrypt(g_netkey, g_iv, 1, 7, seq, g_unicast, g_prov,
                               t, 7, 0x00, npdu);
    if (n) g_send(0x00, npdu, n);
}

static void log_bytes(const char *tag, const uint8_t *b, size_t n) {
    Serial.print(tag);
    for (size_t i = 0; i < n; i++) Serial.printf("%02x", b[i]);
    Serial.println();
}

// ---- the config server: answer what the app expects, capture the secrets ----
static void dispatch(const uint8_t *a, size_t n, bool fromDevkey) {
    uint32_t op; size_t olen;
    if (a[0] < 0x80)            { op = a[0];                       olen = 1; }
    else if ((a[0] & 0xC0) == 0x80) { op = ((uint32_t)a[0] << 8) | a[1]; olen = 2; }
    else                        { op = ((uint32_t)a[0] << 16) | (a[1] << 8) | a[2]; olen = 3; }

    if (!fromDevkey) {                       // AppKey-encrypted: a vendor message
        Serial.printf("[rec] >>> VENDOR write, opcode 0x%06x  ", (unsigned)op);
        log_bytes("params ", a + olen, n - olen);
        return;                              // these carry load-type / motion config
    }

    switch (op) {
    case 0x8008: {                           // Config Composition Data Get
        Serial.println("[rec] <- Composition Data Get; -> Status (mimic a switch)");
        uint8_t c[40]; size_t i = 0;
        c[i++] = 0x02; c[i++] = 0x00;        // Composition Data Status, page 0
        auto le16 = [&](uint16_t v){ c[i++] = v & 0xFF; c[i++] = v >> 8; };
        le16(0x0820); le16(0x0000); le16(0x0000); le16(0x0100); le16(0x0003);
        le16(0x0000);                        // element 0 location
        c[i++] = 4; c[i++] = 1;              // 4 SIG models, 1 vendor
        uint16_t sig[4] = {0x0000, 0x0002, 0x1000, 0x1002};
        for (int k = 0; k < 4; k++) le16(sig[k]);
        le16(0x0820); le16(0x0001);          // vendor company + model
        send_access(c, i, false);            // devkey-encrypted
        break; }
    case 0x0000: {                           // Config AppKey Add
        if (n >= 1 + 3 + 16) {
            memcpy(g_appkey, a + 4, 16); g_haveAppkey = true;
            log_bytes("[rec] *** APPKEY CAPTURED: ", g_appkey, 16);
            Serial.println("    ^ with this we can decode PIR + taps + vendor state");
        }
        uint8_t st[6] = {0x80, 0x03, 0x00, a[1], a[2], a[3]};   // AppKey Status: success
        send_access(st, 6, false);
        break; }
    case 0x803D: {                           // Config Model App Bind
        Serial.println("[rec] <- Model App Bind; -> Status success");
        size_t plen = n - olen;              // elem(2)+appkeyidx(2)+model(2|4)
        uint8_t st[20]; st[0] = 0x80; st[1] = 0x3E; st[2] = 0x00;
        memcpy(st + 3, a + olen, plen);
        send_access(st, 3 + plen, false);
        break; }
    case 0x0003: {                           // Config Model Publication Set
        Serial.println("[rec] <- Publication Set; -> Status success");
        size_t plen = n - olen;
        uint8_t st[28]; st[0] = 0x80; st[1] = 0x19; st[2] = 0x00;
        memcpy(st + 3, a + olen, plen);
        send_access(st, 3 + plen, false);
        break; }
    case 0x8001: {                           // Config AppKey Get -> AppKey List
        // The app checks our AppKeys before adding one. Report none until we
        // capture one, then report index 0 so the add reads back as applied.
        if (g_haveAppkey) {
            uint8_t st[7] = {0x80, 0x02, 0x00, a[olen], a[olen + 1], 0x00, 0x00};
            send_access(st, 7, false);
        } else {
            uint8_t st[5] = {0x80, 0x02, 0x00, a[olen], a[olen + 1]};
            send_access(st, 5, false);
        }
        break; }
    case 0x8042: {                           // Config NetKey Get -> NetKey List
        uint8_t st[4] = {0x80, 0x43, 0x00, 0x00};   // one netkey, index 0
        send_access(st, 4, false); break; }
    case 0x800C: {                           // Default TTL Get -> Status
        uint8_t st[3] = {0x80, 0x0E, 0x07}; send_access(st, 3, false); break; }
    case 0x8009: {                           // Beacon Get -> Status (off)
        uint8_t st[3] = {0x80, 0x0B, 0x00}; send_access(st, 3, false); break; }
    case 0x8012: {                           // GATT Proxy Get -> Status (enabled)
        uint8_t st[3] = {0x80, 0x14, 0x01}; send_access(st, 3, false); break; }
    case 0x8026: {                           // Relay Get -> Status
        uint8_t st[4] = {0x80, 0x28, 0x01, 0x00}; send_access(st, 4, false); break; }
    case 0x800F: {                           // Friend Get -> Status (not supported)
        uint8_t st[3] = {0x80, 0x11, 0x02}; send_access(st, 3, false); break; }
    case 0x8023: {                           // Network Transmit Get -> Status
        uint8_t st[3] = {0x80, 0x25, 0x00}; send_access(st, 3, false); break; }
    case 0x8046: {                           // Node Identity Get -> Status
        uint8_t st[6] = {0x80, 0x48, 0x00, a[olen], a[olen + 1], 0x01};
        send_access(st, 6, false); break; }
    case 0x8038: {                           // Heartbeat Publication Get -> Status
        uint8_t st[11] = {0x80, 0x06, 0x00, 0,0, 0, 0, 0, 0,0, 0};
        send_access(st, 11, false); break; }
    case 0x8049:                             // Config Node Reset: do NOT reset --
        Serial.println("[rec] <- Node Reset (ignored; we are recording, not resetting)");
        break;
    default:
        Serial.printf("[rec] <- config opcode 0x%0*x (unhandled)  ",
                      (int)(olen * 2), (unsigned)op);
        log_bytes("", a + olen, n - olen);
        break;
    }
}

static void handle_upper(const uint8_t *upper, size_t ulen, bool akf,
                         uint32_t seqNonce, uint16_t src, uint8_t szmic) {
    if (akf && !g_haveAppkey) { Serial.println("[rec] appkey msg before appkey"); return; }
    uint8_t out[64]; size_t olen;
    if (mesh_app_decrypt(akf ? g_appkey : g_devkey, !akf, g_iv, seqNonce,
                         src, g_unicast, upper, ulen, szmic ? 8 : 4, out, &olen)) {
        dispatch(out, olen, !akf);
    } else {
        Serial.println("[rec] upper transport decrypt failed");
    }
}

void rec_on_proxy(uint8_t type, const uint8_t *pdu, size_t len) {
    if (type != 0x00) return;                // only network PDUs carry config
    MeshNetMsg m;
    if (!mesh_net_decrypt(g_netkey, g_iv, pdu, len, &m)) return;
    if (g_prov == 0 && m.src != g_unicast) g_prov = m.src;   // learn the app's address
    if (m.dst != g_unicast) return;          // only what's addressed to us

    const uint8_t *t = m.transport;
    if (m.ctl) {
        // control (e.g. our own SegAck echoes / friend); ignore for now
        return;
    }
    bool seg = t[0] & 0x80, akf = t[0] & 0x40;
    if (!seg) {
        handle_upper(t + 1, m.tlen - 1, akf, m.seq, m.src, 0);
        return;
    }
    uint32_t hdr = ((uint32_t)t[1] << 16) | (t[2] << 8) | t[3];
    uint8_t  szmic  = (hdr >> 23) & 1;
    uint16_t seqzero = (hdr >> 10) & 0x1FFF;
    uint8_t  sego = (hdr >> 5) & 0x1F, segn = hdr & 0x1F;
    if (seqzero != rx_seqzero) {
        rx_seqzero = seqzero; rx_mask = 0; rx_segn = segn;
        rx_seq0 = m.seq; rx_szmic = szmic; rx_total = 0;
        memset(rx_buf, 0, sizeof(rx_buf));
    }
    size_t seglen = m.tlen - 4;
    if (sego * 12 + seglen <= sizeof(rx_buf)) memcpy(rx_buf + sego * 12, t + 4, seglen);
    rx_mask |= (1u << sego);
    if (sego == segn) rx_total = sego * 12 + seglen;

    uint32_t full = (segn >= 31) ? 0xFFFFFFFFu : ((1u << (segn + 1)) - 1);
    if ((rx_mask & full) == full && rx_total) {
        send_segack(seqzero, rx_mask);       // tell the app we have it all
        uint32_t seqAuth = (rx_seq0 & ~0x1FFFu) | seqzero;
        if ((rx_seq0 & 0x1FFF) < seqzero) seqAuth -= 0x2000;
        handle_upper(rx_buf, rx_total, akf, seqAuth, m.src, rx_szmic);
        rx_seqzero = 0xFFFF;
    }
}
