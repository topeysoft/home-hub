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

static BLEUUID SVC_PROV((uint16_t)0x1827);
static BLEUUID CH_IN((uint16_t)0x2ADB);    // Provisioning Data In  (write)
static BLEUUID CH_OUT((uint16_t)0x2ADC);   // Provisioning Data Out (notify)

// Provisioning PDU types
enum { P_INVITE=0, P_CAPS=1, P_START=2, P_PUBKEY=3, P_INPUT_COMPLETE=4,
       P_CONFIRM=5, P_RANDOM=6, P_DATA=7, P_COMPLETE=8, P_FAILED=9 };

static BLECharacteristic *chOut = nullptr;

// --- captured protocol transcript pieces (for the confirmation inputs) ---
static uint8_t inviteP[1], capsP[11], startP[5];
static uint8_t provPub[64], devPub[64], secret[32];
static uint8_t confSalt[16], confKey[16], devRandom[16], provConfirm[16];
static uint8_t sessionKey[16], sessionNonce[13];
static bool haveInvite=false;

// A plausible device UUID (Brilliant OUI-flavoured; the panel may or may not filter)
static uint8_t devUUID[16] = {0x42,0x52,0x4c,0x01, 0x7c,0x10,0x15,0x04,
                              0xde,0xad, 0,0,0,0,0,0};

static void put_ble_beacon();  // fwd

// ---- PB-GATT SAR (proxy-style) reassembly of provisioning PDUs ----
static uint8_t rxbuf[128]; static size_t rxlen=0;

static void sendPDU(uint8_t type, const uint8_t *p, size_t n) {
    // PB-GATT: 1 byte (SAR<<6 | msgtype=0x03 Provisioning) then payload
    const uint8_t MSG_PROV = 0x03;
    const size_t room = 20 - 1;
    uint8_t pdu[64]; pdu[0]=type; memcpy(pdu+1, p, n); size_t len=n+1;
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
        // Capabilities: 1 element, algo P-256(0x0001), no pubkey oob, NO static/oob
        uint8_t caps[11] = {1, 0x00,0x01, 0x00, 0x00, 0x00, 0x00,0x00, 0x00, 0x00,0x00};
        memcpy(capsP, caps, 11);
        sendPDU(P_CAPS, caps, 11);
        Serial.println("[prov] -> Capabilities (No-OOB only)");
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
        uint8_t in[32]; memcpy(in, devRandom,16); memset(in+16,0,16); // auth=0 (No OOB)
        uint8_t devConfirm[16]; mesh_cmac(confKey, in, 32, devConfirm);
        sendPDU(P_CONFIRM, devConfirm, 16);
        Serial.println("[prov] <- Provisioner Confirmation; -> our Confirmation");
        break; }
    case P_RANDOM: {
        uint8_t provRandom[16]; memcpy(provRandom, p, 16);
        // verify provisioner confirmation
        uint8_t in[32]; memcpy(in, provRandom,16); memset(in+16,0,16);
        uint8_t chk[16]; mesh_cmac(confKey, in, 32, chk);
        if (memcmp(chk, provConfirm, 16)!=0) { Serial.println("[prov] provisioner confirm MISMATCH"); fail(0x05); return; }
        sendPDU(P_RANDOM, devRandom, 16);
        Serial.println("[prov] <- Provisioner Random (verified); -> our Random");
        // provisioning salt = s1(confSalt || provRandom || devRandom)
        uint8_t ps[48]; memcpy(ps,confSalt,16); memcpy(ps+16,provRandom,16); memcpy(ps+32,devRandom,16);
        uint8_t provSalt[16]; mesh_s1(ps, 48, provSalt);
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
        Serial.println("Copy the NETKEY line. With it we can decrypt the panel's mesh.");
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
    // randomize the low bytes of the device UUID so retries look fresh
    for (int i=10;i<16;i++) devUUID[i]=esp_random();
    Serial.print("device UUID "); for(int i=0;i<16;i++) Serial.printf("%02x", devUUID[i]); Serial.println();

    BLEDevice::init("Brilliant Switch");
    BLEServer *srv = BLEDevice::createServer();
    BLEService *svc = srv->createService(SVC_PROV);
    BLECharacteristic *in = svc->createCharacteristic(CH_IN,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    in->setCallbacks(new InCB());
    chOut = svc->createCharacteristic(CH_OUT, BLECharacteristic::PROPERTY_NOTIFY);
    chOut->addDescriptor(new BLE2902());
    svc->start();
    put_ble_beacon();
    Serial.println("advertising as UNPROVISIONED (0x1827). Run 'Add a device' in the app now.\n");
}

void loop() { delay(1000); }
