#include "mesh_crypto.h"

#include "mbedtls/aes.h"
#include "mbedtls/ccm.h"

static const uint8_t ZERO16[16] = {0};

static void aes_ecb_raw(const uint8_t key[16], const uint8_t in[16],
                        uint8_t out[16]) {
    mbedtls_aes_context a;
    mbedtls_aes_init(&a);
    mbedtls_aes_setkey_enc(&a, key, 128);
    mbedtls_aes_crypt_ecb(&a, MBEDTLS_AES_ENCRYPT, in, out);
    mbedtls_aes_free(&a);
}

// Arduino's prebuilt mbedtls ships without MBEDTLS_CMAC_C, so AES-CMAC is
// implemented here directly (RFC 4493) on top of AES-ECB.
static void shift_left(const uint8_t in[16], uint8_t out[16]) {
    uint8_t carry = 0;
    for (int i = 15; i >= 0; i--) {
        out[i] = (uint8_t)((in[i] << 1) | carry);
        carry = (in[i] & 0x80) ? 1 : 0;
    }
}

void mesh_cmac(const uint8_t key[16], const uint8_t *msg, size_t len,
               uint8_t out[16]) {
    uint8_t L[16] = {0}, K1[16], K2[16], X[16] = {0}, blk[16];
    aes_ecb_raw(key, L, L);

    shift_left(L, K1);
    if (L[0] & 0x80) K1[15] ^= 0x87;
    shift_left(K1, K2);
    if (K1[0] & 0x80) K2[15] ^= 0x87;

    size_t n = (len + 15) / 16;
    bool complete = (n != 0) && (len % 16 == 0);
    if (n == 0) n = 1;

    for (size_t i = 0; i + 1 < n; i++) {
        for (int j = 0; j < 16; j++) blk[j] = X[j] ^ msg[i * 16 + j];
        aes_ecb_raw(key, blk, X);
    }

    uint8_t last[16] = {0};
    size_t rem = len - (n - 1) * 16;
    if (complete) {
        memcpy(last, msg + (n - 1) * 16, 16);
        for (int j = 0; j < 16; j++) last[j] ^= K1[j];
    } else {
        if (rem) memcpy(last, msg + (n - 1) * 16, rem);
        last[rem] = 0x80;
        for (int j = 0; j < 16; j++) last[j] ^= K2[j];
    }
    for (int j = 0; j < 16; j++) blk[j] = X[j] ^ last[j];
    aes_ecb_raw(key, blk, out);
}

void mesh_s1(const uint8_t *msg, size_t len, uint8_t out[16]) {
    mesh_cmac(ZERO16, msg, len, out);
}

void mesh_k1(const uint8_t *n, size_t nlen, const uint8_t salt[16],
             const uint8_t *p, size_t plen, uint8_t out[16]) {
    uint8_t t[16];
    mesh_cmac(salt, n, nlen, t);
    mesh_cmac(t, p, plen, out);
}

void mesh_k2(const uint8_t netkey[16], uint8_t *nid, uint8_t enc[16],
             uint8_t priv[16]) {
    uint8_t salt[16], t[16], t1[16], buf[64];
    mesh_s1((const uint8_t *)"smk2", 4, salt);
    mesh_cmac(salt, netkey, 16, t);

    buf[0] = 0x00;
    buf[1] = 0x01;
    mesh_cmac(t, buf, 2, t1);                 // T1 = CMAC(T, P || 0x01), P = 0x00

    memcpy(buf, t1, 16);
    buf[16] = 0x00;
    buf[17] = 0x02;
    mesh_cmac(t, buf, 18, enc);               // T2

    memcpy(buf, enc, 16);
    buf[16] = 0x00;
    buf[17] = 0x03;
    mesh_cmac(t, buf, 18, priv);              // T3

    *nid = t1[15] & 0x7F;
}

void mesh_k3(const uint8_t netkey[16], uint8_t out[8]) {
    uint8_t salt[16], t[16], full[16];
    mesh_s1((const uint8_t *)"smk3", 4, salt);
    mesh_cmac(salt, netkey, 16, t);
    const uint8_t p[] = {'i', 'd', '6', '4', 0x01};
    mesh_cmac(t, p, sizeof(p), full);
    memcpy(out, full + 8, 8);
}

uint8_t mesh_k4(const uint8_t appkey[16]) {
    uint8_t salt[16], t[16], full[16];
    mesh_s1((const uint8_t *)"smk4", 4, salt);
    mesh_cmac(salt, appkey, 16, t);
    const uint8_t p[] = {'i', 'd', '6', 0x01};
    mesh_cmac(t, p, sizeof(p), full);
    return full[15] & 0x3F;
}

static void aes_ecb(const uint8_t key[16], const uint8_t in[16], uint8_t out[16]) {
    mbedtls_aes_context a;
    mbedtls_aes_init(&a);
    mbedtls_aes_setkey_enc(&a, key, 128);
    mbedtls_aes_crypt_ecb(&a, MBEDTLS_AES_ENCRYPT, in, out);
    mbedtls_aes_free(&a);
}

static bool ccm_enc(const uint8_t key[16], const uint8_t *nonce, size_t nlen,
                    const uint8_t *in, size_t ilen, uint8_t taglen,
                    uint8_t *out) {
    mbedtls_ccm_context c;
    mbedtls_ccm_init(&c);
    if (mbedtls_ccm_setkey(&c, MBEDTLS_CIPHER_ID_AES, key, 128) != 0) {
        mbedtls_ccm_free(&c);
        return false;
    }
    int rc = mbedtls_ccm_encrypt_and_tag(&c, ilen, nonce, nlen, NULL, 0, in, out,
                                         out + ilen, taglen);
    mbedtls_ccm_free(&c);
    return rc == 0;
}

static bool ccm_dec(const uint8_t key[16], const uint8_t *nonce, size_t nlen,
                    const uint8_t *ct, size_t ctlen, uint8_t taglen,
                    uint8_t *out) {
    if (ctlen < taglen) return false;
    size_t plen = ctlen - taglen;
    mbedtls_ccm_context c;
    mbedtls_ccm_init(&c);
    if (mbedtls_ccm_setkey(&c, MBEDTLS_CIPHER_ID_AES, key, 128) != 0) {
        mbedtls_ccm_free(&c);
        return false;
    }
    int rc = mbedtls_ccm_auth_decrypt(&c, plen, nonce, nlen, NULL, 0, ct, out,
                                      ct + plen, taglen);
    mbedtls_ccm_free(&c);
    return rc == 0;
}

size_t mesh_net_encrypt(const uint8_t netkey[16], uint32_t iv, uint8_t ctl,
                        uint8_t ttl, uint32_t seq, uint16_t src, uint16_t dst,
                        const uint8_t *transport, size_t tlen, uint8_t nonce_type,
                        uint8_t *out) {
    uint8_t nid, ek[16], pk[16];
    mesh_k2(netkey, &nid, ek, pk);

    uint8_t nonce[13];
    nonce[0] = nonce_type;
    nonce[1] = (uint8_t)((ctl << 7) | (ttl & 0x7F));
    nonce[2] = (seq >> 16) & 0xFF;
    nonce[3] = (seq >> 8) & 0xFF;
    nonce[4] = seq & 0xFF;
    nonce[5] = src >> 8;
    nonce[6] = src & 0xFF;
    nonce[7] = 0;
    nonce[8] = 0;
    nonce[9] = (iv >> 24) & 0xFF;
    nonce[10] = (iv >> 16) & 0xFF;
    nonce[11] = (iv >> 8) & 0xFF;
    nonce[12] = iv & 0xFF;

    uint8_t plain[32];
    plain[0] = dst >> 8;
    plain[1] = dst & 0xFF;
    memcpy(plain + 2, transport, tlen);
    size_t plen = tlen + 2;
    uint8_t miclen = ctl ? 8 : 4;

    uint8_t enc[48];
    if (!ccm_enc(ek, nonce, 13, plain, plen, miclen, enc)) return 0;
    size_t enclen = plen + miclen;

    uint8_t pp[16] = {0};
    pp[5] = (iv >> 24) & 0xFF;
    pp[6] = (iv >> 16) & 0xFF;
    pp[7] = (iv >> 8) & 0xFF;
    pp[8] = iv & 0xFF;
    memcpy(pp + 9, enc, 7);
    uint8_t pecb[16];
    aes_ecb(pk, pp, pecb);

    uint8_t hdr[6];
    hdr[0] = (uint8_t)((ctl << 7) | (ttl & 0x7F));
    hdr[1] = (seq >> 16) & 0xFF;
    hdr[2] = (seq >> 8) & 0xFF;
    hdr[3] = seq & 0xFF;
    hdr[4] = src >> 8;
    hdr[5] = src & 0xFF;

    out[0] = (uint8_t)(((iv & 1) << 7) | nid);
    for (int i = 0; i < 6; i++) out[1 + i] = hdr[i] ^ pecb[i];
    memcpy(out + 7, enc, enclen);
    return 7 + enclen;
}

bool mesh_net_decrypt(const uint8_t netkey[16], uint32_t iv, const uint8_t *pdu,
                      size_t len, MeshNetMsg *out) {
    if (len < 10) return false;
    uint8_t nid, ek[16], pk[16];
    mesh_k2(netkey, &nid, ek, pk);
    if ((pdu[0] & 0x7F) != nid) return false;

    const uint8_t *enc = pdu + 7;
    size_t enclen = len - 7;

    uint8_t pp[16] = {0};
    pp[5] = (iv >> 24) & 0xFF;
    pp[6] = (iv >> 16) & 0xFF;
    pp[7] = (iv >> 8) & 0xFF;
    pp[8] = iv & 0xFF;
    memcpy(pp + 9, enc, 7);
    uint8_t pecb[16];
    aes_ecb(pk, pp, pecb);

    uint8_t hdr[6];
    for (int i = 0; i < 6; i++) hdr[i] = pdu[1 + i] ^ pecb[i];

    uint8_t ctl = hdr[0] >> 7;
    uint8_t ttl = hdr[0] & 0x7F;
    uint32_t seq = ((uint32_t)hdr[1] << 16) | ((uint32_t)hdr[2] << 8) | hdr[3];
    uint16_t src = ((uint16_t)hdr[4] << 8) | hdr[5];

    uint8_t nonce[13];
    nonce[0] = 0x00;
    nonce[1] = hdr[0];
    memcpy(nonce + 2, hdr + 1, 3);
    memcpy(nonce + 5, hdr + 4, 2);
    nonce[7] = 0;
    nonce[8] = 0;
    nonce[9] = (iv >> 24) & 0xFF;
    nonce[10] = (iv >> 16) & 0xFF;
    nonce[11] = (iv >> 8) & 0xFF;
    nonce[12] = iv & 0xFF;

    uint8_t miclen = ctl ? 8 : 4;
    uint8_t plain[48];
    if (!ccm_dec(ek, nonce, 13, enc, enclen, miclen, plain)) return false;

    size_t plen = enclen - miclen;
    if (plen < 3 || plen - 2 > sizeof(out->transport)) return false;
    out->ctl = ctl;
    out->ttl = ttl;
    out->seq = seq;
    out->src = src;
    out->dst = ((uint16_t)plain[0] << 8) | plain[1];
    out->tlen = plen - 2;
    memcpy(out->transport, plain + 2, out->tlen);
    return true;
}

static void app_nonce(bool is_devkey, uint32_t iv, uint32_t seq, uint16_t src,
                      uint16_t dst, uint8_t nonce[13]) {
    nonce[0] = is_devkey ? 0x02 : 0x01;
    nonce[1] = 0x00;
    nonce[2] = (seq >> 16) & 0xFF;
    nonce[3] = (seq >> 8) & 0xFF;
    nonce[4] = seq & 0xFF;
    nonce[5] = src >> 8;
    nonce[6] = src & 0xFF;
    nonce[7] = dst >> 8;
    nonce[8] = dst & 0xFF;
    nonce[9] = (iv >> 24) & 0xFF;
    nonce[10] = (iv >> 16) & 0xFF;
    nonce[11] = (iv >> 8) & 0xFF;
    nonce[12] = iv & 0xFF;
}

size_t mesh_app_encrypt(const uint8_t key[16], bool is_devkey, uint32_t iv,
                        uint32_t seq, uint16_t src, uint16_t dst,
                        const uint8_t *access, size_t alen, uint8_t *out) {
    uint8_t nonce[13];
    app_nonce(is_devkey, iv, seq, src, dst, nonce);
    if (!ccm_enc(key, nonce, 13, access, alen, 4, out)) return 0;
    return alen + 4;
}

bool mesh_app_decrypt(const uint8_t key[16], bool is_devkey, uint32_t iv,
                      uint32_t seq, uint16_t src, uint16_t dst,
                      const uint8_t *ct, size_t clen, uint8_t tag_len,
                      uint8_t *out, size_t *olen) {
    uint8_t nonce[13];
    app_nonce(is_devkey, iv, seq, src, dst, nonce);
    if (!ccm_dec(key, nonce, 13, ct, clen, tag_len, out)) return false;
    *olen = clen - tag_len;
    return true;
}

// ---- self-test against Mesh Profile 1.0.1 section 8.1 sample data ----
static bool eq(const uint8_t *a, const char *hex, size_t n) {
    for (size_t i = 0; i < n; i++) {
        char b[3] = {hex[i * 2], hex[i * 2 + 1], 0};
        if (a[i] != (uint8_t)strtol(b, NULL, 16)) return false;
    }
    return true;
}

bool mesh_selftest(Stream &s) {
    bool ok = true;
    uint8_t o[16];

    mesh_s1((const uint8_t *)"test", 4, o);
    bool p = eq(o, "b73cefbd641ef2ea598c2b6efb62f79c", 16);
    s.printf("  s1  %s\n", p ? "PASS" : "FAIL");
    ok &= p;

    const uint8_t n[16] = {0xf7, 0xa2, 0xa4, 0x4f, 0x8e, 0x8a, 0x80, 0x29,
                           0x06, 0x4f, 0x17, 0x3d, 0xdc, 0x1e, 0x2b, 0x00};
    uint8_t nid, ek[16], pk[16];
    mesh_k2(n, &nid, ek, pk);
    p = (nid == 0x7f) && eq(ek, "9f589181a0f50de73c8070c7a6d27f46", 16) &&
        eq(pk, "4c715bd4a64b938f99b453351653124f", 16);
    s.printf("  k2  %s (nid 0x%02x)\n", p ? "PASS" : "FAIL", nid);
    ok &= p;

    uint8_t id[8];
    mesh_k3(n, id);
    p = eq(id, "ff046958233db014", 8);
    s.printf("  k3  %s\n", p ? "PASS" : "FAIL");
    ok &= p;

    const uint8_t a[16] = {0x32, 0x16, 0xd1, 0x50, 0x98, 0x84, 0xb5, 0x33,
                           0x24, 0x85, 0x41, 0x79, 0x2b, 0x87, 0x7f, 0x98};
    uint8_t aid = mesh_k4(a);
    p = (aid == 0x38);
    s.printf("  k4  %s (aid 0x%02x)\n", p ? "PASS" : "FAIL", aid);
    ok &= p;
    return ok;
}

bool mesh_prov_ccm_decrypt(const uint8_t key[16], const uint8_t nonce[13],
                           const uint8_t *ct, size_t ctlen, uint8_t out[25]) {
    // provisioning data is 25 bytes + 8-byte MIC = 33 bytes ciphertext
    if (ctlen != 33) return false;
    return ccm_dec(key, nonce, 13, ct, ctlen, 8, out);
}

// ---- ECDH P-256 (provisioning key exchange) ----
#include "mbedtls/ecdh.h"
#include "mbedtls/ecp.h"
#include "mbedtls/entropy.h"
#include "mbedtls/ctr_drbg.h"

static mbedtls_ecp_keypair g_kp;
static bool g_kp_ready = false;

bool ecdh_generate(uint8_t pub_xy[64]) {
    mbedtls_entropy_context ent; mbedtls_ctr_drbg_context drbg;
    mbedtls_entropy_init(&ent); mbedtls_ctr_drbg_init(&drbg);
    const char *pers = "mesh-prov";
    if (mbedtls_ctr_drbg_seed(&drbg, mbedtls_entropy_func, &ent,
            (const unsigned char*)pers, strlen(pers)) != 0) return false;
    mbedtls_ecp_keypair_init(&g_kp);
    if (mbedtls_ecp_group_load(&g_kp.grp, MBEDTLS_ECP_DP_SECP256R1) != 0) return false;
    if (mbedtls_ecp_gen_keypair(&g_kp.grp, &g_kp.d, &g_kp.Q,
            mbedtls_ctr_drbg_random, &drbg) != 0) return false;
    if (mbedtls_mpi_write_binary(&g_kp.Q.X, pub_xy, 32) != 0) return false;
    if (mbedtls_mpi_write_binary(&g_kp.Q.Y, pub_xy + 32, 32) != 0) return false;
    g_kp_ready = true;
    mbedtls_ctr_drbg_free(&drbg); mbedtls_entropy_free(&ent);
    return true;
}

bool ecdh_shared(const uint8_t peer_xy[64], uint8_t secret[32]) {
    if (!g_kp_ready) return false;
    mbedtls_ecp_point peer; mbedtls_mpi z;
    mbedtls_ecp_point_init(&peer); mbedtls_mpi_init(&z);
    bool ok = false;
    do {
        if (mbedtls_mpi_read_binary(&peer.X, peer_xy, 32) != 0) break;
        if (mbedtls_mpi_read_binary(&peer.Y, peer_xy + 32, 32) != 0) break;
        if (mbedtls_mpi_lset(&peer.Z, 1) != 0) break;
        if (mbedtls_ecdh_compute_shared(&g_kp.grp, &z, &peer, &g_kp.d,
                NULL, NULL) != 0) break;
        if (mbedtls_mpi_write_binary(&z, secret, 32) != 0) break;
        ok = true;
    } while (0);
    mbedtls_ecp_point_free(&peer); mbedtls_mpi_free(&z);
    return ok;
}
