#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read the Provisioning Capabilities PDU from an unprovisioned SIG mesh node.

Non-destructive: sends Provisioning Invite (attention=0) over PB-GATT and decodes
the Capabilities reply. Does NOT provision -- it just asks the node what it supports.
Decisive question: does it require an OOB key we don't have?
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

PROV_SVC = "00001827-0000-1000-8000-00805f9b34fb"
DATA_IN = "00002adb-0000-1000-8000-00805f9b34fb"   # write w/o response
DATA_OUT = "00002adc-0000-1000-8000-00805f9b34fb"  # notify

PROXY_HDR_PROV = 0x03  # SAR=complete(0), type=Provisioning PDU(3)
PDU_INVITE = 0x00
PDU_CAPABILITIES = 0x01

ALGOS = {0: "BTM_ECDH_P256_CMAC_AES128_AES_CCM (Mesh 1.0)",
         1: "BTM_ECDH_P256_HMAC_SHA256_AES_CCM (Mesh 1.1)"}
OUT_ACTS = {0: "Blink", 1: "Beep", 2: "Vibrate", 3: "Output Numeric",
            4: "Output Alphanumeric"}
IN_ACTS = {0: "Push", 1: "Twist", 2: "Input Numeric", 3: "Input Alphanumeric"}

got = None


def bits(val, names):
    out = [n for b, n in names.items() if val & (1 << b)]
    return ", ".join(out) if out else "none"


def decode(p):
    # p = Capabilities payload, 11 bytes after the 1-byte PDU type
    (elems, algos, pubkey, static, o_size, o_act, i_size, i_act) = (
        p[0], int.from_bytes(p[1:3], "big"), p[3], p[4],
        p[5], int.from_bytes(p[6:8], "big"),
        p[8], int.from_bytes(p[9:11], "big"))
    print(f"  Elements           : {elems}")
    print(f"  Algorithms         : 0x{algos:04x}  {bits(algos, ALGOS)}")
    print(f"  Public Key Type    : 0x{pubkey:02x}  "
          f"{'OOB public key AVAILABLE' if pubkey & 1 else 'no OOB public key (inband only)'}")
    print(f"  Static OOB Type    : 0x{static:02x}  "
          f"{'static OOB AVAILABLE' if static & 1 else 'no static OOB'}")
    print(f"  Output OOB         : size={o_size} actions=0x{o_act:04x} {bits(o_act, OUT_ACTS)}")
    print(f"  Input OOB          : size={i_size} actions=0x{i_act:04x} {bits(i_act, IN_ACTS)}")
    print()
    if not (pubkey & 1) and not (static & 1) and o_size == 0 and i_size == 0:
        print("  => No OOB required. ANY standard provisioner can claim this node.")
    else:
        print("  => Node offers OOB methods; 'No OOB' may still be selectable by the provisioner.")


def on_notify(_, data: bytearray):
    got.put_nowait(bytes(data))


async def main():
    global got
    got = asyncio.Queue()
    print("looking for an unprovisioned mesh node (0x1827)...")
    dev = await BleakScanner.find_device_by_filter(
        lambda d, ad: PROV_SVC in [u.lower() for u in (ad.service_uuids or [])],
        timeout=30.0)
    if not dev:
        print("none found. Is the switch still in unprovisioned mode?")
        return
    print(f"found {dev.address}  {dev.name!r}\nconnecting...")

    async with BleakClient(dev, timeout=30.0) as cli:
        await cli.start_notify(DATA_OUT, on_notify)
        # Provisioning Invite, attention duration 0s
        await cli.write_gatt_char(DATA_IN,
                                  bytes([PROXY_HDR_PROV, PDU_INVITE, 0x00]),
                                  response=False)
        try:
            pdu = await asyncio.wait_for(got.get(), timeout=15.0)
        except asyncio.TimeoutError:
            print("no Capabilities reply within 15s")
            return
        print(f"raw: {pdu.hex()}")
        if len(pdu) >= 2 and (pdu[0] & 0x3F) == PROXY_HDR_PROV and pdu[1] == PDU_CAPABILITIES:
            print("\n=== Provisioning Capabilities ===")
            decode(pdu[2:])
        else:
            print("unexpected PDU (not Capabilities)")
        await cli.stop_notify(DATA_OUT)


asyncio.run(main())
