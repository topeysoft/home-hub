#!/usr/bin/env python3
"""Bluetooth SIG Mesh crypto + PB-GATT primitives (Mesh Profile 1.0.1, s3.8).

Enough of the stack to provision a node and talk to it. No BlueZ needed --
works anywhere bleak works, macOS included.
"""
import json
import os
import struct

from cryptography.hazmat.primitives import cmac
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

ZERO16 = b"\x00" * 16


# ---------- primitives (Mesh Profile 3.8.2) ----------

def aes_cmac(key: bytes, msg: bytes) -> bytes:
    c = cmac.CMAC(algorithms.AES(key))
    c.update(msg)
    return c.finalize()


def s1(m: bytes) -> bytes:
    return aes_cmac(ZERO16, m)


def k1(n: bytes, salt: bytes, p: bytes) -> bytes:
    return aes_cmac(aes_cmac(salt, n), p)


def k2(n: bytes, p: bytes):
    """-> (nid, encryption_key, privacy_key)"""
    salt = s1(b"smk2")
    t = aes_cmac(salt, n)
    t1 = aes_cmac(t, p + b"\x01")
    t2 = aes_cmac(t, t1 + p + b"\x02")
    t3 = aes_cmac(t, t2 + p + b"\x03")
    return t1[15] & 0x7F, t2, t3


def k3(n: bytes) -> bytes:
    """8-byte Network ID."""
    salt = s1(b"smk3")
    t = aes_cmac(salt, n)
    return aes_cmac(t, b"id64\x01")[8:]


def k4(n: bytes) -> int:
    """6-bit AID."""
    salt = s1(b"smk4")
    t = aes_cmac(salt, n)
    return aes_cmac(t, b"id6\x01")[15] & 0x3F


def ccm_encrypt(key, nonce, plain, aad=b"", tag=8):
    return AESCCM(key, tag_length=tag).encrypt(nonce, plain, aad or None)


def ccm_decrypt(key, nonce, ct, aad=b"", tag=8):
    return AESCCM(key, tag_length=tag).decrypt(nonce, ct, aad or None)


# ---------- network layer (Mesh Profile 3.4.4 / 3.8.7) ----------

def net_encrypt(netkey, iv_index, ctl, ttl, seq, src, dst, transport_pdu,
                nonce_type=0x00):
    nid, ek, pk = k2(netkey, b"\x00")
    ivi = iv_index & 1
    # Proxy Nonce (type 0x03) has a fixed 0x00 pad in octet 1, NOT CTL|TTL --
    # that field only belongs in the Network Nonce (type 0x00). Getting this
    # wrong makes proxy-config messages undecryptable by spec-correct firmware
    # (our own tolerant switches accepted it; the real panel switches did not,
    # so "open the filter" silently failed and nothing was ever forwarded).
    b1 = 0x00 if nonce_type == 0x03 else ((ctl << 7) | (ttl & 0x7F))
    nonce = bytes([nonce_type, b1]) + seq.to_bytes(3, "big") \
        + src.to_bytes(2, "big") + b"\x00\x00" + iv_index.to_bytes(4, "big")
    mic_len = 8 if ctl else 4
    enc = ccm_encrypt(ek, nonce, dst.to_bytes(2, "big") + transport_pdu,
                      tag=mic_len)
    # obfuscate the (CTL|TTL, SEQ, SRC) header
    privacy_plain = b"\x00" * 5 + iv_index.to_bytes(4, "big") + enc[:7]
    pecb = _aes_ecb(pk, privacy_plain)
    hdr = bytes([(ctl << 7) | (ttl & 0x7F)]) + seq.to_bytes(3, "big") \
        + src.to_bytes(2, "big")
    obf = bytes(a ^ b for a, b in zip(hdr, pecb[:6]))
    return bytes([(ivi << 7) | nid]) + obf + enc


def net_decrypt(netkey, iv_index, pdu, nonce_type=0x00):
    nid, ek, pk = k2(netkey, b"\x00")
    if (pdu[0] & 0x7F) != nid:
        return None
    obf, enc = pdu[1:7], pdu[7:]
    privacy_plain = b"\x00" * 5 + iv_index.to_bytes(4, "big") + enc[:7]
    pecb = _aes_ecb(pk, privacy_plain)
    hdr = bytes(a ^ b for a, b in zip(obf, pecb[:6]))
    ctl, ttl = hdr[0] >> 7, hdr[0] & 0x7F
    seq = int.from_bytes(hdr[1:4], "big")
    src = int.from_bytes(hdr[4:6], "big")
    nonce = bytes([nonce_type, hdr[0]]) + hdr[1:4] + hdr[4:6] + b"\x00\x00" \
        + iv_index.to_bytes(4, "big")
    try:
        dec = ccm_decrypt(ek, nonce, enc, tag=8 if ctl else 4)
    except Exception:
        return None
    return {"ctl": ctl, "ttl": ttl, "seq": seq, "src": src,
            "dst": int.from_bytes(dec[:2], "big"), "transport": dec[2:]}


def _aes_ecb(key, block):
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    e = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return e.update(block[:16]) + e.finalize()


# ---------- upper transport, device-key messages (3.6) ----------

def app_encrypt_devkey(devkey, iv_index, seq, src, dst, access_pdu):
    nonce = b"\x02\x00" + seq.to_bytes(3, "big") + src.to_bytes(2, "big") \
        + dst.to_bytes(2, "big") + iv_index.to_bytes(4, "big")
    return ccm_encrypt(devkey, nonce, access_pdu, tag=4)


def app_decrypt_devkey(devkey, iv_index, seq, src, dst, ct, tag=4):
    nonce = b"\x02\x00" + seq.to_bytes(3, "big") + src.to_bytes(2, "big") \
        + dst.to_bytes(2, "big") + iv_index.to_bytes(4, "big")
    return ccm_decrypt(devkey, nonce, ct, tag=tag)


def seq_auth(seq, seqzero):
    """Full 24-bit SeqAuth from a segment's SEQ and its 13-bit SeqZero."""
    base = (seq & ~0x1FFF) | seqzero
    return base - 0x2000 if (seq & 0x1FFF) < seqzero else base


# ---------- state ----------

# The network keys are secrets and must never live in the repo. Default to the
# user's config dir; override with BRILLIANT_MESH_STORE.
STORE = os.environ.get("BRILLIANT_MESH_STORE") or os.path.expanduser(
    "~/.config/brilliant-mesh/mesh-net.json")


def load():
    if os.path.exists(STORE):
        with open(STORE) as f:
            return json.load(f)
    net = {
        "netkey": os.urandom(16).hex(),
        "appkey": os.urandom(16).hex(),
        "key_index": 0,
        "iv_index": 0,
        "flags": 0,
        "provisioner_addr": 1,
        "next_addr": 2,
        "seq": 0,
        "nodes": {},
    }
    save(net)
    return net


def save(net):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w") as f:
        json.dump(net, f, indent=2)


def next_seq(net):
    net["seq"] += 1
    save(net)
    return net["seq"]


def app_encrypt_appkey(appkey, iv_index, seq, src, dst, access_pdu):
    nonce = b"\x01\x00" + seq.to_bytes(3, "big") + src.to_bytes(2, "big") \
        + dst.to_bytes(2, "big") + iv_index.to_bytes(4, "big")
    return ccm_encrypt(appkey, nonce, access_pdu, tag=4)


def pack_key_indexes(net_idx, app_idx):
    return bytes([net_idx & 0xFF,
                  ((net_idx >> 8) & 0x0F) | ((app_idx & 0x0F) << 4),
                  (app_idx >> 4) & 0xFF])
