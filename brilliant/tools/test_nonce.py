#!/usr/bin/env python3
"""Prove the application nonce is built correctly, for the cases that used to fail.

`explore.try_decrypt` once built the nonce with our own address as the
destination and ASZMIC hardcoded to zero. Both are invisible failures: the
decrypt raises, the listener skips, and the screen says the switch sent nothing.
These are the three shapes a Brilliant event could take that the old code would
have thrown away.

    python3 tools/test_nonce.py
"""
import os
import sys

import explore
import mesh


class Ctx:
    """The fields try_decrypt reads off a Node."""

    def __init__(self):
        self.appkey = os.urandom(16)
        self.devkey = os.urandom(16)
        self.netkey = os.urandom(16)
        self.src = 0x0001
        self.iv = 0


NODE = 0x0002
ok = True


def chk(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"{'PASS' if good else 'FAIL'}  {name}")
    if not good:
        print(f"      got  {got.hex() if got else None}\n      want {want.hex()}")


def unsegmented(n, dst, access, seq=1234):
    aid = mesh.k4(n.appkey)
    upper = mesh.app_encrypt_appkey(n.appkey, n.iv, seq, NODE, dst, access)
    assert len(upper) <= 15, "too long for an unsegmented access message"
    return {"src": NODE, "dst": dst, "seq": seq, "ctl": 0,
            "transport": bytes([0x40 | aid]) + upper}


def segmented(n, dst, access, seq0=5000, szmic=1):
    """Yield the segments of one long access message, in order."""
    aid = mesh.k4(n.appkey)
    seqzero = seq0 & 0x1FFF
    nonce = bytes([0x01, 0x80 if szmic else 0x00]) + seq0.to_bytes(3, "big") \
        + NODE.to_bytes(2, "big") + dst.to_bytes(2, "big") \
        + n.iv.to_bytes(4, "big")
    upper = mesh.ccm_encrypt(n.appkey, nonce, access, tag=8 if szmic else 4)
    parts = [upper[i:i + 12] for i in range(0, len(upper), 12)]
    segn = len(parts) - 1
    for i, part in enumerate(parts):
        hdr = (szmic << 23) | (seqzero << 10) | (i << 5) | segn
        yield {"src": NODE, "dst": dst, "seq": seq0 + i, "ctl": 0,
               "transport": bytes([0xC0 | aid]) + hdr.to_bytes(3, "big") + part}


def main():
    n = Ctx()
    status = bytes([0x82, 0x04, 0x01])              # Generic OnOff Status, on

    # A publication aimed anywhere must decode, not just one aimed at us.
    for dst, label in ((0x0001, "unicast to us"),
                       (0xC000, "group 0xC000"),
                       (0xFFFF, "all-nodes 0xFFFF")):
        chk(f"unsegmented Status published to {label}",
            explore.try_decrypt(n, unsegmented(n, dst, status)), status)

    # A long vendor event, segmented, with a 64-bit MIC.
    event = bytes([0xC1, 0x20, 0x08]) + bytes(range(16))
    for dst, label in ((0x0001, "us"), (0xC000, "group 0xC000")):
        explore.segs.clear()
        out = None
        for seg in segmented(n, dst, event):
            out = explore.try_decrypt(n, seg)
        chk(f"segmented SZMIC=1 vendor event to {label}", out, event)

    # And a short one with the 32-bit MIC, so the ASZMIC fix did not break it.
    explore.segs.clear()
    out = None
    for seg in segmented(n, 0x0001, event, szmic=0):
        out = explore.try_decrypt(n, seg)
    chk("segmented SZMIC=0 vendor event to us", out, event)

    print("\nALL PASS" if ok else "\nFAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
