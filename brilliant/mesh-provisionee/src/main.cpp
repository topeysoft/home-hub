// Mesh provisionee — pose as a fresh Brilliant switch and capture the netkey.
//
// The Brilliant Control panel is alive and is a working mesh provisioner. When
// "Add a device" runs in the app, the panel provisions a new node and hands it
// the network key. We present as an unprovisioned device over PB-GATT, let the
// panel provision us, and print the netkey it delivers. With that key, the panel's
// whole mesh (every switch's PIR + tap-state) becomes decryptable.
//
// This is the device side of the same protocol our provision.py drives; the
// crypto (CMAC/k1/CCM, verified against the SIG vectors) is shared, plus ECDH.

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "esp_random.h"

#include "mesh_crypto.h"
#include "recorder.h"
#include "mbedtls/aes.h"

static BLEUUID SVC_PROV((uint16_t)0x1827);
static BLEUUID CH_IN((uint16_t)0x2ADB);    // Provisioning Data In  (write)
static BLEUUID CH_OUT((uint16_t)0x2ADC);   // Provisioning Data Out (notify)
static BLEUUID SVC_PROXY((uint16_t)0x1828);  // Mesh Proxy Service (post-provisioning)
static BLEUUID CH_PIN((uint16_t)0x2ADD);   // Proxy Data In  (write)
static BLEUUID CH_POUT((uint16_t)0x2ADE);  // Proxy Data Out (notify)

// Provisioning PDU types
enum { P_INVITE=0, P_CAPS=1, P_START=2, P_PUBKEY=3, P_INPUT_COMPLETE=4,
       P_CONFIRM=5, P_RANDOM=6, P_DATA=7, P_COMPLETE=8, P_FAILED=9 };

static BLECharacteristic *chOut = nullptr;

// --- captured protocol transcript pieces (for the confirmation inputs) ---
static uint8_t inviteP[1], capsP[11], startP[5];
static uint8_t provPub[64], devPub[64], secret[32];
static uint8_t confSalt[16], confKey[16], devRandom[16], provConfirm[16];
static uint8_t sessionKey[16], sessionNonce[13];
static uint8_t provSalt[16];                 // needed later to derive our DevKey
static bool haveInvite=false;

// Captured at provisioning; consumed by the recorder once we flip to proxy mode.
static uint8_t  capNetkey[16], capDevkey[16];
static uint16_t capUnicast = 0;
static uint32_t capIv = 0;
static volatile bool gotProvisioned = false;   // set in a BLE callback, acted on in loop()
static bool recorderRunning = false;
static BLECharacteristic *proxyOut = nullptr;

// Device UUID + Static OOB, both read from a real switch's QR code.
//
// A Brilliant QR is 32 bytes: the first 16 are the Device UUID, the last 16 are
// a 128-bit Static OOB secret. The app scans the QR, looks for a device
// advertising that UUID, and provisions it with Static OOB using that secret.
// So to be added via the app's primary (QR) flow, our beacon must carry the
// UUID the user scans, and we must answer the confirmation with the matching
// OOB value -- which is what makes this an authentic-looking device rather than
// the No-OOB impostor the app filtered out before.
//
// These two lines ARE the identity of one physical switch. Whichever switch's
// QR you scan in the app, put its 32 bytes here, and keep that physical switch
// from advertising unprovisioned at the same time or the app sees two devices
// with the same UUID (which is exactly what happened the first time).
//   QR: 017e420e39c80007b0d86cdb5d3c622b 2fb5427e3db145bd8d325dccf3cc456d
static uint8_t devUUID[16]   = {0x01,0x7e,0x42,0x0e, 0x39,0xc8,0x00,0x07,
                                0xb0,0xd8,0x6c,0xdb, 0x5d,0x3c,0x62,0x2b};
static uint8_t staticOOB[16] = {0x2f,0xb5,0x42,0x7e, 0x3d,0xb1,0x45,0xbd,
                                0x8d,0x32,0x5d,0xcc, 0xf3,0xcc,0x45,0x6d};

static void put_ble_beacon();  // fwd
static void advertise_proxy(); // fwd

// AuthValue for the provisioning confirmation. The Brilliant app, holding the
// OOB from the QR, selects Authentication Method 0x01 (Static OOB) in its Start
// PDU; we then place the 16-byte OOB secret where a No-OOB device puts zeros.
// If a provisioner ever chooses No-OOB (method 0x00), fall back to zeros so the
// listen-after-reset flow still works. startP[2] is the Authentication Method.
static void fill_auth(uint8_t out[16]) {
    if (startP[2] == 0x01) memcpy(out, staticOOB, 16);
    else                   memset(out, 0, 16);
}

// ---- PB-GATT SAR (proxy-style) reassembly of provisioning PDUs ----
static uint8_t rxbuf[128]; static size_t rxlen=0;

static void sendPDU(uint8_t type, const uint8_t *p, size_t n) {
    // PB-GATT: 1 byte (SAR<<6 | msgtype=0x03 Provisioning) then payload
    const uint8_t MSG_PROV = 0x03;
    const size_t room = 20 - 1;
    // Must hold type(1) + payload. The largest provisioning payload is the
    // 64-byte Public Key, so pdu needs 65 bytes; [64] overflowed by one and the
    // stack canary aborted mid-provisioning. Earlier No-OOB attempts died at
    // discovery and never reached the Public Key send, so this stayed latent.
    uint8_t pdu[80]; pdu[0]=type; memcpy(pdu+1, p, n); size_t len=n+1;
    if (len <= room) {
        uint8_t out[24]; out[0]=MSG_PROV; memcpy(out+1,pdu,len);
        chOut->setValue(out, len+1); chOut->notify(); return;
    }
    size_t off=0, idx=0, total=(len+room-1)/room;
    while (off<len) {
        size_t c = min(room, len-off);
        uint8_t sar = idx==0?1: (idx==total-1?3:2);
        uint8_t out[24]; out[0]=(sar<<6)|MSG_PROV; memcpy(out+1, pdu+off, c);
        chOut->setValue(out, c+1); chOut->notify();
        off+=c; idx++; delay(15);
    }
}

static void fail(uint8_t code){ uint8_t e[1]={code}; sendPDU(P_FAILED,e,1);
    Serial.printf("[prov] FAILED 0x%02x\n", code); }

static void handleProvPDU(const uint8_t *d, size_t n) {
    if (n < 1) return;
    uint8_t type = d[0]; const uint8_t *p = d+1; size_t plen = n-1;
    switch (type) {
    case P_INVITE: {
        inviteP[0] = p[0]; haveInvite=true;
        Serial.printf("[prov] <- Invite (attention %u)\n", p[0]);
        // Capabilities: 1 element, algo P-256(0x0001), no pubkey OOB, Static OOB
        // AVAILABLE (byte 4 = 0x01). A real Brilliant switch declares Static OOB
        // because its QR carries the secret; declaring it lets the app choose
        // method 0x01 and provision us for real. (No-OOB is still accepted if a
        // provisioner picks it -- see fill_auth.)
        uint8_t caps[11] = {1, 0x00,0x01, 0x00, 0x01, 0x00, 0x00,0x00, 0x00, 0x00,0x00};
        memcpy(capsP, caps, 11);
        sendPDU(P_CAPS, caps, 11);
        Serial.println("[prov] -> Capabilities (Static OOB available)");
        break; }
    case P_START:
        memcpy(startP, p, 5);
        Serial.printf("[prov] <- Start (algo %u pubkey %u auth %u)\n", p[0],p[1],p[2]);
        break;
    case P_PUBKEY: {
        memcpy(provPub, p, 64);
        if (!ecdh_generate(devPub)) { fail(0x08); return; }
        sendPDU(P_PUBKEY, devPub, 64);
        Serial.println("[prov] <- Provisioner PublicKey; -> our PublicKey");
        if (!ecdh_shared(provPub, secret)) { fail(0x07); return; }
        // confirmation inputs = invite||caps||start||provPub||devPub
        uint8_t ci[1+11+5+64+64]; size_t o=0;
        memcpy(ci+o, inviteP,1); o+=1; memcpy(ci+o, capsP,11); o+=11;
        memcpy(ci+o, startP,5); o+=5; memcpy(ci+o, provPub,64); o+=64;
        memcpy(ci+o, devPub,64); o+=64;
        mesh_s1(ci, o, confSalt);
        mesh_k1(secret, 32, confSalt, (const uint8_t*)"prck", 4, confKey);
        break; }
    case P_CONFIRM: {
        memcpy(provConfirm, p, 16);
        for (int i=0;i<16;i++) devRandom[i]=esp_random();
        uint8_t in[32]; memcpy(in, devRandom,16); fill_auth(in+16); // Static OOB / No-OOB
        uint8_t devConfirm[16]; mesh_cmac(confKey, in, 32, devConfirm);
        sendPDU(P_CONFIRM, devConfirm, 16);
        Serial.println("[prov] <- Provisioner Confirmation; -> our Confirmation");
        break; }
    case P_RANDOM: {
        uint8_t provRandom[16]; memcpy(provRandom, p, 16);
        // verify provisioner confirmation
        uint8_t in[32]; memcpy(in, provRandom,16); fill_auth(in+16);
        uint8_t chk[16]; mesh_cmac(confKey, in, 32, chk);
        if (memcmp(chk, provConfirm, 16)!=0) { Serial.println("[prov] provisioner confirm MISMATCH"); fail(0x05); return; }
        sendPDU(P_RANDOM, devRandom, 16);
        Serial.println("[prov] <- Provisioner Random (verified); -> our Random");
        // provisioning salt = s1(confSalt || provRandom || devRandom)
        uint8_t ps[48]; memcpy(ps,confSalt,16); memcpy(ps+16,provRandom,16); memcpy(ps+32,devRandom,16);
        mesh_s1(ps, 48, provSalt);           // file-scope: reused to derive DevKey
        mesh_k1(secret, 32, provSalt, (const uint8_t*)"prsk", 4, sessionKey);
        uint8_t nonce16[16]; mesh_k1(secret, 32, provSalt, (const uint8_t*)"prsn", 4, nonce16);
        memcpy(sessionNonce, nonce16+3, 13);
        break; }
    case P_DATA: {
        // encrypted provisioning data: 25 bytes + 8 MIC
        uint8_t plain[25];
        if (!mesh_prov_ccm_decrypt(sessionKey, sessionNonce, p, plen, plain)) {
            Serial.println("[prov] provisioning data decrypt FAILED"); fail(0x07); return;
        }
        sendPDU(P_COMPLETE, nullptr, 0);
        Serial.println("\n================= NETKEY CAPTURED =================");
        Serial.print("NETKEY  "); for(int i=0;i<16;i++) Serial.printf("%02x", plain[i]); Serial.println();
        uint16_t keyIdx = plain[16]|(plain[17]<<8);
        uint8_t flags = plain[18];
        uint32_t ivIndex = (plain[19]<<24)|(plain[20]<<16)|(plain[21]<<8)|plain[22];
        uint16_t unicast = (plain[23]<<8)|plain[24];
        Serial.printf("keyIndex 0x%04x  flags 0x%02x  ivIndex 0x%08x  unicast 0x%04x\n",
                      keyIdx, flags, ivIndex, unicast);
        Serial.println("==================================================");

        // DevKey = k1(ECDH secret, ProvisioningSalt, "prdk"). With the netkey and
        // our devkey we can now receive and answer the app's configuration, which
        // is where the AppKey and the vendor (load-type / motion) writes arrive.
        memcpy(capNetkey, plain, 16);
        mesh_k1(secret, 32, provSalt, (const uint8_t*)"prdk", 4, capDevkey);
        capUnicast = unicast; capIv = ivIndex;
        gotProvisioned = true;   // loop() switches us to proxy/recorder mode
        Serial.println("Provisioned. Switching to proxy so the app can configure us...");
        break; }
    default:
        Serial.printf("[prov] <- unexpected PDU type %u\n", type);
    }
}

class InCB : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *c) override {
        std::string v = c->getValue();
        if (v.empty()) return;
        uint8_t hdr = (uint8_t)v[0]; uint8_t sar = (hdr>>6)&3;
        const uint8_t *pl = (const uint8_t*)v.data()+1; size_t n=v.size()-1;
        if (sar==0){ handleProvPDU(pl,n); return; }
        if (sar==1){ rxlen=0; }
        if (rxlen+n<sizeof(rxbuf)){ memcpy(rxbuf+rxlen,pl,n); rxlen+=n; }
        if (sar==3){ handleProvPDU(rxbuf,rxlen); rxlen=0; }
    }
};

// ---- proxy (post-provisioning): the app reconnects here to configure us ----

// Send a proxy PDU to the app as GATT notifications, with proxy SAR framing.
static void send_proxy(uint8_t type, const uint8_t *pdu, size_t len) {
    if (!proxyOut) return;
    const size_t room = 19;                       // fits ATT MTU 23; larger MTUs are fine too
    if (len <= room) {
        uint8_t out[24]; out[0] = type;           // SAR 00 (complete) | type
        memcpy(out + 1, pdu, len);
        proxyOut->setValue(out, len + 1); proxyOut->notify();
        return;
    }
    size_t off = 0, idx = 0, total = (len + room - 1) / room;
    while (off < len) {
        size_t c = (len - off < room) ? (len - off) : room;
        uint8_t sar = (idx == 0) ? 1 : ((idx == total - 1) ? 3 : 2);
        uint8_t out[24]; out[0] = (sar << 6) | type;
        memcpy(out + 1, pdu + off, c);
        proxyOut->setValue(out, c + 1); proxyOut->notify();
        off += c; idx++; delay(15);
    }
}

// Re-advertise on disconnect: after provisioning the app drops the link and
// reconnects to the proxy service, and the ESP32 stack does not auto-restart
// advertising. Advertise proxy once provisioned, provisioning otherwise.
class SrvCB : public BLEServerCallbacks {
    void onConnect(BLEServer *) override { Serial.println("[ble] central connected"); }
    void onDisconnect(BLEServer *) override {
        Serial.println("[ble] central disconnected; re-advertising");
        delay(80);
        if (recorderRunning) advertise_proxy(); else put_ble_beacon();
    }
};

static uint8_t proxyRx[320]; static size_t proxyRxLen = 0; static uint8_t proxyRxType = 0;

class ProxyInCB : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *c) override {
        std::string v = c->getValue();
        if (v.empty()) return;
        uint8_t hdr = (uint8_t)v[0]; uint8_t sar = (hdr >> 6) & 3; uint8_t type = hdr & 0x3F;
        const uint8_t *pl = (const uint8_t *)v.data() + 1; size_t n = v.size() - 1;
        if (sar == 0) { rec_on_proxy(type, pl, n); return; }
        if (sar == 1) { proxyRxLen = 0; proxyRxType = type; }
        if (proxyRxLen + n < sizeof(proxyRx)) { memcpy(proxyRx + proxyRxLen, pl, n); proxyRxLen += n; }
        if (sar == 3) { rec_on_proxy(proxyRxType, proxyRx, proxyRxLen); proxyRxLen = 0; }
    }
};

// Stop advertising the provisioning service; advertise the Mesh Proxy Service
// with Network ID identity, so the app reconnects to finish configuring us.
static void aes_ecb(const uint8_t key[16], const uint8_t in[16], uint8_t out[16]) {
    mbedtls_aes_context c; mbedtls_aes_init(&c);
    mbedtls_aes_setkey_enc(&c, key, 128);
    mbedtls_aes_crypt_ecb(&c, MBEDTLS_AES_ENCRYPT, in, out);
    mbedtls_aes_free(&c);
}

// Advertise the Mesh Proxy Service with a NODE IDENTITY beacon, so the app can
// recognise THIS node as the one it just provisioned and reconnect promptly.
// A Network ID beacon (what we sent before) only says "some node on this net",
// so the app could not match it to the node it provisioned -- it timed out
// after ~60s and reconnected in cleanup mode (Config Node Reset). Node Identity
// is the spec's post-provisioning advertisement.
//   IdentityKey = k1(NetKey, s1("nkik"), "id128"||0x01)
//   Hash        = AES-ECB(IdentityKey, 0*6 || Random(8) || Address(2))[8:16]
static void advertise_proxy() {
    BLEAdvertising *a = BLEDevice::getAdvertising();
    a->stop();
    uint8_t salt[16]; mesh_s1((const uint8_t *)"nkik", 4, salt);
    uint8_t P[6] = {'i','d','1','2','8',0x01};
    uint8_t idKey[16]; mesh_k1(capNetkey, 16, salt, P, 6, idKey);
    uint8_t rnd[8]; for (int i = 0; i < 8; i++) rnd[i] = esp_random();
    uint8_t in[16]; memset(in, 0, 6); memcpy(in + 6, rnd, 8);
    in[14] = capUnicast >> 8; in[15] = capUnicast & 0xFF;
    uint8_t h[16]; aes_ecb(idKey, in, h);

    BLEAdvertisementData adv; adv.setFlags(0x06);
    adv.setCompleteServices(SVC_PROXY);
    std::string sd; sd.push_back((char)0x01);     // Node Identity type
    sd.append((const char *)(h + 8), 8);          // Hash (rightmost 8 bytes)
    sd.append((const char *)rnd, 8);              // Random
    adv.setServiceData(SVC_PROXY, sd);
    BLEAdvertisementData rsp; rsp.setName("Brilliant Switch");
    a->setAdvertisementData(adv);
    a->setScanResponseData(rsp);
    a->setScanResponse(true);
    a->start();
    Serial.println("[rec] advertising PROXY with NODE IDENTITY -- app can match "
                   "and reconnect to the node it just provisioned");
}

static void put_ble_beacon() {
    BLEAdvertisementData adv;
    adv.setFlags(0x06);
    adv.setCompleteServices(SVC_PROV);            // PB-GATT discovery
    // PB-ADV Unprovisioned Device beacon: AD type 0x2B, beacon type 0x00,
    // 16-byte Device UUID, 2-byte OOB info. This is how mesh provisioners
    // (very likely the Brilliant panel) discover unprovisioned devices.
    std::string beacon; beacon.push_back((char)0x14); // len: type+beacontype+uuid+oob = 20
    beacon.push_back((char)0x2B);                     // AD type: Mesh Beacon
    beacon.push_back((char)0x00);                     // beacon type: Unprovisioned Device
    beacon.append((const char*)devUUID, 16);
    beacon.push_back((char)0x00); beacon.push_back((char)0x00); // OOB info
    adv.addData(beacon);
    // Scan response carries the PB-GATT service-data (device UUID + OOB)
    BLEAdvertisementData rsp;
    std::string sd; sd.resize(18);
    memcpy(&sd[0], devUUID, 16); sd[16]=0; sd[17]=0;
    rsp.setServiceData(SVC_PROV, sd);
    rsp.setName("Brilliant Switch");
    BLEAdvertising *a = BLEDevice::getAdvertising();
    a->setAdvertisementData(adv);
    a->setScanResponseData(rsp);
    a->setScanResponse(true);
    a->start();
}

void setup() {
    Serial.begin(115200); delay(400);
    Serial.println("\n=== Mesh provisionee (pose as fresh Brilliant switch) ===");
    Serial.println("crypto self-test:");
    if (!mesh_selftest(Serial)) Serial.println("  !! CRYPTO BROKEN");
    Serial.print("device UUID "); for(int i=0;i<16;i++) Serial.printf("%02x", devUUID[i]); Serial.println();

    BLEDevice::init("Brilliant Switch");
    BLEServer *srv = BLEDevice::createServer();
    srv->setCallbacks(new SrvCB());
    BLEService *svc = srv->createService(SVC_PROV);
    BLECharacteristic *in = svc->createCharacteristic(CH_IN,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    in->setCallbacks(new InCB());
    chOut = svc->createCharacteristic(CH_OUT, BLECharacteristic::PROPERTY_NOTIFY);
    chOut->addDescriptor(new BLE2902());
    svc->start();

    // Proxy service, ready for the app to reconnect to after provisioning.
    BLEService *psvc = srv->createService(SVC_PROXY);
    BLECharacteristic *pin = psvc->createCharacteristic(CH_PIN,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    pin->setCallbacks(new ProxyInCB());
    proxyOut = psvc->createCharacteristic(CH_POUT, BLECharacteristic::PROPERTY_NOTIFY);
    proxyOut->addDescriptor(new BLE2902());
    psvc->start();
    rec_set_sender(send_proxy);

    put_ble_beacon();
    Serial.println("advertising as UNPROVISIONED (0x1827). Run 'Add a device' in the app now.\n");
}

void loop() {
    if (gotProvisioned && !recorderRunning) {
        recorderRunning = true;
        rec_init(capNetkey, capDevkey, capUnicast, capIv);
        advertise_proxy();
        Serial.println("[rec] recorder live. Finish 'Add a device' in the app; "
                       "watch for APPKEY CAPTURED and vendor writes.\n");
    }
    delay(500);
}
