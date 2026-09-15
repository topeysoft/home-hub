// auto-generated: real source text + CommonCrypto AES, run on the Mac
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <stdlib.h>
#include <CommonCrypto/CommonCryptor.h>

static const uint8_t ZERO16[16] = {0};

static void aes_ecb_raw(const uint8_t key[16], const uint8_t in[16], uint8_t out[16]) {
    size_t moved = 0;
    CCCrypt(kCCEncrypt, kCCAlgorithmAES, kCCOptionECBMode, key, 16, NULL,
            in, 16, out, 16, &moved);
}

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

static int fails = 0;
static void chk(const char *name, const uint8_t *got, const char *want, int n) {
    char hex[80] = {0};
    for (int i = 0; i < n; i++) sprintf(hex + i * 2, "%02x", got[i]);
    int ok = strcmp(hex, want) == 0;
    if (!ok) fails++;
    printf("%s  %-8s %s\n", ok ? "PASS" : "FAIL", name, ok ? "" : hex);
    if (!ok) printf("              want %s\n", want);
}

int main(void) {
    uint8_t o[16];
    mesh_s1((const uint8_t *)"test", 4, o);
    chk("s1", o, "b73cefbd641ef2ea598c2b6efb62f79c", 16);

    // RFC 4493 AES-CMAC vectors (exercise empty / partial / exact blocks)
    const uint8_t k[16] = {0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,
                           0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c};
    mesh_cmac(k, NULL, 0, o);
    chk("cmac-0", o, "bb1d6929e95937287fa37d129b756746", 16);
    const uint8_t m16[16] = {0x6b,0xc1,0xbe,0xe2,0x2e,0x40,0x9f,0x96,
                             0xe9,0x3d,0x7e,0x11,0x73,0x93,0x17,0x2a};
    mesh_cmac(k, m16, 16, o);
    chk("cmac-16", o, "070a16b46b4d4144f79bdd9dd04a287c", 16);
    mesh_cmac(k, m16, 10, o);
    chk("cmac-10", o, "c1390a10ad5aa66d13dd5d85f5ee04ae", 16);

    // RFC 4493 example 3: 40 bytes -- spans multiple blocks with a partial tail
    const uint8_t m40[40] = {
        0x6b,0xc1,0xbe,0xe2,0x2e,0x40,0x9f,0x96,0xe9,0x3d,0x7e,0x11,0x73,0x93,0x17,0x2a,
        0xae,0x2d,0x8a,0x57,0x1e,0x03,0xac,0x9c,0x9e,0xb7,0x6f,0xac,0x45,0xaf,0x8e,0x51,
        0x30,0xc8,0x1c,0x46,0xa3,0x5c,0xe4,0x11};
    mesh_cmac(k, m40, 40, o);
    chk("cmac-40", o, "dfa66747de9ae63030ca32611497c827", 16);

    const uint8_t n[16] = {0xf7,0xa2,0xa4,0x4f,0x8e,0x8a,0x80,0x29,
                           0x06,0x4f,0x17,0x3d,0xdc,0x1e,0x2b,0x00};
    uint8_t nid, ek[16], pk[16];
    mesh_k2(n, &nid, ek, pk);
    printf("%s  k2-nid   0x%02x\n", nid == 0x7f ? "PASS" : "FAIL", nid);
    if (nid != 0x7f) fails++;
    chk("k2-enc", ek, "9f589181a0f50de73c8070c7a6d27f46", 16);
    chk("k2-priv", pk, "4c715bd4a64b938f99b453351653124f", 16);

    uint8_t id[8]; mesh_k3(n, id);
    chk("k3", id, "ff046958233db014", 8);

    const uint8_t a[16] = {0x32,0x16,0xd1,0x50,0x98,0x84,0xb5,0x33,
                           0x24,0x85,0x41,0x79,0x2b,0x87,0x7f,0x98};
    uint8_t aid = mesh_k4(a);
    printf("%s  k4       0x%02x\n", aid == 0x38 ? "PASS" : "FAIL", aid);
    if (aid != 0x38) fails++;

    printf("\n%s\n", fails ? "FAILURES -- firmware crypto is wrong" : "ALL PASS");
    return fails;
}
