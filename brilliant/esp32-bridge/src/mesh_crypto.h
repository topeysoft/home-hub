// Bluetooth SIG Mesh crypto, ESP32 / mbedtls.
// Mirrors mesh.py exactly -- verified against the spec's section 8.1 vectors.
#pragma once
#include <Arduino.h>

void mesh_cmac(const uint8_t key[16], const uint8_t *msg, size_t len,
               uint8_t out[16]);
void mesh_s1(const uint8_t *msg, size_t len, uint8_t out[16]);
void mesh_k1(const uint8_t *n, size_t nlen, const uint8_t salt[16],
             const uint8_t *p, size_t plen, uint8_t out[16]);
void mesh_k2(const uint8_t netkey[16], uint8_t *nid, uint8_t enc[16],
             uint8_t priv[16]);
void mesh_k3(const uint8_t netkey[16], uint8_t out[8]);
uint8_t mesh_k4(const uint8_t appkey[16]);

// Secure Network Beacon (3.9.3): BeaconKey = k1(NetKey, s1("nkbk"), "id128" || 0x01).
// `beacon` is the 21 bytes after the beacon-type octet: flags, network id, iv index, auth.
void mesh_beacon_key(const uint8_t netkey[16], uint8_t out[16]);
bool mesh_beacon_verify(const uint8_t netkey[16], const uint8_t beacon[21]);

// Network layer. Returns length written to out, or 0 on failure.
size_t mesh_net_encrypt(const uint8_t netkey[16], uint32_t iv, uint8_t ctl,
                        uint8_t ttl, uint32_t seq, uint16_t src, uint16_t dst,
                        const uint8_t *transport, size_t tlen, uint8_t nonce_type,
                        uint8_t *out);

struct MeshNetMsg {
    uint8_t ctl, ttl;
    uint32_t seq;
    uint16_t src, dst;
    uint8_t transport[32];
    size_t tlen;
};
bool mesh_net_decrypt(const uint8_t netkey[16], uint32_t iv, const uint8_t *pdu,
                      size_t len, MeshNetMsg *out);

// Upper transport (access messages). A tag_len of 8 on decrypt means the
// message was segmented with SZMIC=1, and the nonce's ASZMIC bit follows it.
size_t mesh_app_encrypt(const uint8_t key[16], bool is_devkey, uint32_t iv,
                        uint32_t seq, uint16_t src, uint16_t dst,
                        const uint8_t *access, size_t alen, uint8_t *out);
bool mesh_app_decrypt(const uint8_t key[16], bool is_devkey, uint32_t iv,
                      uint32_t seq, uint16_t src, uint16_t dst,
                      const uint8_t *ct, size_t clen, uint8_t tag_len,
                      uint8_t *out, size_t *olen);
bool mesh_selftest(Stream &s);
