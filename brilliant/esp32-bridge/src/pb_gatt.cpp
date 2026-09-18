#include "pb_gatt.h"

static NimBLEUUID SVC_PROV((uint16_t)0x1827);
static NimBLEUUID SVC_PROXY((uint16_t)0x1828);
static NimBLEUUID CH_PROV_IN("00002adb-0000-1000-8000-00805f9b34fb");
static NimBLEUUID CH_PROV_OUT("00002adc-0000-1000-8000-00805f9b34fb");

// The proxy bearer's framing, one message type along: the low six bits say what
// kind of message this is and the top two carry SAR. 0x03 is Provisioning PDU.
static const uint8_t MSG_PROV = 0x03;

// Incoming PDUs land in a NimBLE callback on another task; the handshake runs on
// the loop. One PDU is in flight at a time in this protocol, so a single slot
// with a flag is enough and a queue would be pretending otherwise.
static volatile bool rx_ready = false;
static uint8_t rx_buf[Provisioner::MAX_PDU];
static volatile size_t rx_len = 0;
static uint8_t sar_buf[Provisioner::MAX_PDU];
static size_t sar_len = 0;

static void prov_notify(NimBLERemoteCharacteristic *c, uint8_t *data, size_t len, bool) {
    (void)c;
    if (len < 1) return;
    const uint8_t sar = (data[0] & 0xC0) >> 6;
    const uint8_t *p = data + 1;
    const size_t n = len - 1;

    if (sar == 0b00) {                       // whole message in one write
        if (n > sizeof(rx_buf)) return;
        memcpy(rx_buf, p, n);
        rx_len = n;
        rx_ready = true;
        return;
    }
    if (sar == 0b01) sar_len = 0;            // first segment
    if (sar_len + n <= sizeof(sar_buf)) {
        memcpy(sar_buf + sar_len, p, n);
        sar_len += n;
    } else {
        sar_len = sizeof(sar_buf) + 1;       // poisoned: too long to be real
    }
    if (sar == 0b11) {                       // last segment
        if (sar_len <= sizeof(rx_buf)) {
            memcpy(rx_buf, sar_buf, sar_len);
            rx_len = sar_len;
            rx_ready = true;
        }
        sar_len = 0;
    }
}

static bool send_pdu(NimBLERemoteCharacteristic *in, uint16_t mtu,
                     const uint8_t *pdu, size_t len) {
    // one ATT write of (type || pdu) when it fits, otherwise SAR. The usable
    // payload is MTU minus the ATT opcode and handle, minus our own type byte.
    const size_t room = (mtu > 6 ? mtu - 3 : 20) - 1;
    uint8_t buf[256];
    if (len <= room) {
        buf[0] = MSG_PROV;
        memcpy(buf + 1, pdu, len);
        return in->writeValue(buf, len + 1, false);
    }
    const size_t total = (len + room - 1) / room;
    for (size_t i = 0, off = 0; i < total; i++) {
        const size_t n = (len - off < room) ? (len - off) : room;
        const uint8_t sar = (i == 0) ? 0b01 : ((i == total - 1) ? 0b11 : 0b10);
        buf[0] = (uint8_t)((sar << 6) | MSG_PROV);
        memcpy(buf + 1, pdu + off, n);
        if (!in->writeValue(buf, n + 1, false)) return false;
        off += n;
        delay(10);                            // the device is a small radio, not a socket
    }
    return true;
}

// One scan, everything it heard, sorted strongest first. Every lookup in this
// file comes through here so there is exactly one place that knows what a
// Brilliant switch's advertisement looks like.
//
// `our_netid` may be null when the caller only wants claimable switches, in
// which case a claimed one is reported as Foreign rather than wrongly as Ours.
static size_t scan_nearby(uint32_t ms, const uint8_t *our_netid, Nearby *out, size_t max) {
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->setActiveScan(true);
    NimBLEScanResults found = scan->start(ms / 1000, false);
    size_t n = 0;
    for (int i = 0; i < found.getCount() && n < max; i++) {
        NimBLEAdvertisedDevice d = found.getDevice(i);
        if (!d.haveServiceData()) continue;

        Nearby row;
        bool got = false;
        for (int k = 0; k < (int)d.getServiceDataCount(); k++) {
            const NimBLEUUID u = d.getServiceDataUUID(k);
            const std::string sd = d.getServiceData(k);

            // Unprovisioned: the Device UUID is the first 16 bytes, and the two
            // after it are OOB info we do not need -- the QR, when there is one,
            // already told us the secret.
            if (u.equals(SVC_PROV) && sd.size() >= 16) {
                row.state = Nearby::Unclaimed;
                memcpy(row.uuid, sd.data(), 16);
                got = true;
                break;
            }
            // Provisioned: a Network ID beacon, type 0x00, then eight bytes of
            // k3(netkey). Anything else under 0x1828 is a Node Identity beacon,
            // which is per-node and says nothing about whose network it is on.
            if (u.equals(SVC_PROXY) && sd.size() >= 9 && sd[0] == 0x00) {
                memcpy(row.netid, sd.data() + 1, 8);
                row.state = (our_netid && memcmp(row.netid, our_netid, 8) == 0)
                                ? Nearby::Ours : Nearby::Foreign;
                got = true;
                break;
            }
        }
        if (!got) continue;

        row.addr = d.getAddress();
        row.rssi = d.getRSSI();
        row.found = true;
        out[n++] = row;
    }
    scan->clearResults();

    for (size_t i = 1; i < n; i++) {         // strongest first: the one nearest the
        Nearby key = out[i];                 // panel is the likeliest to be theirs,
        size_t j = i;                        // and it is only an ordering, not a choice
        while (j > 0 && out[j - 1].rssi < key.rssi) { out[j] = out[j - 1]; j--; }
        out[j] = key;
    }
    return n;
}

size_t pb_gatt_survey(uint32_t ms, const uint8_t our_netid[8], Nearby *out, size_t max) {
    return scan_nearby(ms, our_netid, out, max);
}

size_t pb_gatt_find_all(uint32_t ms, Nearby *out, size_t max) {
    Nearby all[12];
    const size_t seen = scan_nearby(ms, nullptr, all, 12);
    size_t n = 0;
    for (size_t i = 0; i < seen && n < max; i++) {
        if (all[i].state == Nearby::Unclaimed) out[n++] = all[i];
    }
    return n;
}

Nearby pb_gatt_find(uint32_t ms, const uint8_t *want_uuid) {
    Nearby all[12];
    const size_t n = pb_gatt_find_all(ms, all, 12);
    if (!want_uuid) return n ? all[0] : Nearby();
    for (size_t i = 0; i < n; i++) {
        if (memcmp(all[i].uuid, want_uuid, 16) == 0) return all[i];
    }
    return Nearby();                          // the code named a switch we cannot hear
}

bool pb_gatt_blink(const Nearby &who, uint8_t seconds) {
    if (!who.found || who.state != Nearby::Unclaimed || seconds == 0) return false;
    NimBLEClient *cli = NimBLEDevice::createClient();
    bool ok = false;
    do {
        if (!cli->connect(who.addr)) break;
        NimBLERemoteService *svc = cli->getService(SVC_PROV);
        if (!svc) break;
        NimBLERemoteCharacteristic *in = svc->getCharacteristic(CH_PROV_IN);
        if (!in) break;

        // An Invite and nothing else. The device starts its attention timer and
        // waits for a Start it will never get; dropping the link leaves it to
        // time out and go back to advertising unclaimed, which is exactly the
        // state we found it in. Nothing about it is changed by being asked.
        const uint8_t pdu[2] = {0x00, seconds};
        ok = send_pdu(in, cli->getMTU(), pdu, 2);
        if (ok) delay((uint32_t)seconds * 1000);
    } while (0);
    cli->disconnect();
    NimBLEDevice::deleteClient(cli);
    return ok;
}

bool pb_gatt_provision(const Nearby &who, Provisioner &p, uint32_t timeout_ms) {
    // A claimed switch has no provisioning service to talk to; refusing here is
    // clearer than a connection that succeeds and then finds nothing.
    if (!who.found || who.state != Nearby::Unclaimed) return false;
    rx_ready = false;
    rx_len = 0;
    sar_len = 0;

    NimBLEClient *cli = NimBLEDevice::createClient();
    bool ok = false;
    do {
        if (!cli->connect(who.addr)) break;
        NimBLERemoteService *svc = cli->getService(SVC_PROV);
        if (!svc) break;
        NimBLERemoteCharacteristic *in = svc->getCharacteristic(CH_PROV_IN);
        NimBLERemoteCharacteristic *out = svc->getCharacteristic(CH_PROV_OUT);
        if (!in || !out || !out->canNotify()) break;
        if (!out->subscribe(true, prov_notify)) break;
        const uint16_t mtu = cli->getMTU();

        const uint32_t deadline = millis() + timeout_ms;
        uint8_t pdu[Provisioner::MAX_PDU];
        while (millis() < deadline) {
            size_t n;
            while ((n = p.next(pdu)) > 0) {
                // a refused write is the link going away, not a protocol fault:
                // leave the state alone and let the deadline end it as unfinished
                if (!send_pdu(in, mtu, pdu, n)) break;
                delay(20);
            }
            if (p.state() == Provisioner::DONE || p.state() == Provisioner::FAILED) break;
            if (rx_ready) {
                uint8_t copy[Provisioner::MAX_PDU];
                const size_t len = rx_len;
                memcpy(copy, rx_buf, len);
                rx_ready = false;
                p.feed(copy, len);
                continue;
            }
            delay(20);
        }
        ok = p.state() == Provisioner::DONE;
    } while (0);

    cli->disconnect();
    NimBLEDevice::deleteClient(cli);
    return ok;
}
