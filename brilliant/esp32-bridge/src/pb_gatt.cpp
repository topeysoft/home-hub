#include "pb_gatt.h"

static NimBLEUUID SVC_PROV((uint16_t)0x1827);
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

// One scan, every unclaimed switch it heard, sorted strongest first. Both the
// list and the by-UUID lookup come from here so there is one place that knows
// what the service data looks like.
static size_t scan_unclaimed(uint32_t ms, Unclaimed *out, size_t max) {
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->setActiveScan(true);
    NimBLEScanResults found = scan->start(ms / 1000, false);
    size_t n = 0;
    for (int i = 0; i < found.getCount() && n < max; i++) {
        NimBLEAdvertisedDevice d = found.getDevice(i);
        if (!d.haveServiceData()) continue;

        // The Device UUID is the first 16 bytes of the Mesh Provisioning Service
        // Data; the two after it are OOB info, which we do not need because the
        // QR -- when there is one -- already told us the secret.
        std::string sd;
        bool got = false;
        for (int k = 0; k < (int)d.getServiceDataCount(); k++) {
            if (d.getServiceDataUUID(k).equals(SVC_PROV)) {
                sd = d.getServiceData(k);
                got = true;
                break;
            }
        }
        if (!got || sd.size() < 16) continue;

        out[n].addr = d.getAddress();
        memcpy(out[n].uuid, sd.data(), 16);
        out[n].rssi = d.getRSSI();
        out[n].found = true;
        n++;
    }
    scan->clearResults();

    for (size_t i = 1; i < n; i++) {         // strongest first: the one nearest the
        Unclaimed key = out[i];              // panel is the likeliest to be theirs,
        size_t j = i;                        // and it is only an ordering, not a choice
        while (j > 0 && out[j - 1].rssi < key.rssi) { out[j] = out[j - 1]; j--; }
        out[j] = key;
    }
    return n;
}

size_t pb_gatt_find_all(uint32_t ms, Unclaimed *out, size_t max) {
    return scan_unclaimed(ms, out, max);
}

Unclaimed pb_gatt_find(uint32_t ms, const uint8_t *want_uuid) {
    Unclaimed all[8];
    const size_t n = scan_unclaimed(ms, all, 8);
    if (!want_uuid) return n ? all[0] : Unclaimed();
    for (size_t i = 0; i < n; i++) {
        if (memcmp(all[i].uuid, want_uuid, 16) == 0) return all[i];
    }
    return Unclaimed();                       // the code named a switch we cannot hear
}

bool pb_gatt_blink(const Unclaimed &who, uint8_t seconds) {
    if (!who.found || seconds == 0) return false;
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

bool pb_gatt_provision(const Unclaimed &who, Provisioner &p, uint32_t timeout_ms) {
    if (!who.found) return false;
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
