#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provision an unprovisioned SIG mesh node over PB-GATT, from macOS.

Claims a factory-reset Brilliant switch into a mesh network we own. Keys are
persisted to mesh-net.json so they can later be imported into bluetooth-meshd
rather than re-provisioning the house.

usage: provision.py [--dry-run]
"""
import asyncio
import os
import sys

from bleak import BleakClient, BleakScanner
from cryptography.hazmat.primitives.asymmetric import ec

import ble
import mesh

PROV_SVC = "00001827-0000-1000-8000-00805f9b34fb"
DATA_IN = "00002adb-0000-1000-8000-00805f9b34fb"
DATA_OUT = "00002adc-0000-1000-8000-00805f9b34fb"

MSG_PROV = 0x03
T_INVITE, T_CAPS, T_START, T_PUBKEY = 0x00, 0x01, 0x02, 0x03
T_INPUTCOMP, T_CONFIRM, T_RANDOM, T_DATA, T_COMPLETE, T_FAILED = (
    0x04, 0x05, 0x06, 0x07, 0x08, 0x09)

FAIL = {0x01: "Prohibited", 0x02: "Invalid PDU", 0x03: "Invalid Format",
        0x04: "Unexpected PDU", 0x05: "Confirmation Failed",
        0x06: "Out of Resources", 0x07: "Decryption Failed",
        0x08: "Unexpected Error", 0x09: "Cannot Assign Addresses"}

DRY = "--dry-run" in sys.argv

rx = None
_buf = bytearray()


def on_notify(_, data: bytearray):
    global _buf
    sar = (data[0] & 0xC0) >> 6
    payload = bytes(data[1:])
    if sar == 0b00:
        rx.put_nowait(payload)
    elif sar == 0b01:
        _buf = bytearray(payload)
    elif sar == 0b10:
        _buf += payload
    else:
        _buf += payload
        rx.put_nowait(bytes(_buf))


async def send(cli, pdu, mtu):
    room = mtu - 3 - 1
    if len(pdu) <= room:
        await cli.write_gatt_char(DATA_IN, bytes([MSG_PROV]) + pdu, response=False)
        return
    chunks = [pdu[i:i + room] for i in range(0, len(pdu), room)]
    for i, c in enumerate(chunks):
        sar = 0b01 if i == 0 else (0b11 if i == len(chunks) - 1 else 0b10)
        await cli.write_gatt_char(DATA_IN, bytes([(sar << 6) | MSG_PROV]) + c,
                                  response=False)
        await asyncio.sleep(0.02)


async def expect(want, label, timeout=20.0):
    try:
        pdu = await asyncio.wait_for(rx.get(), timeout=timeout)
    except asyncio.TimeoutError:
        raise RuntimeError(f"timeout waiting for {label}")
    if pdu[0] == T_FAILED:
        code = pdu[1] if len(pdu) > 1 else 0
        raise RuntimeError(f"Provisioning Failed 0x{code:02x} "
                           f"{FAIL.get(code, '?')} (during {label})")
    if pdu[0] != want:
        raise RuntimeError(f"expected {label} (0x{want:02x}), got 0x{pdu[0]:02x}")
    print(f"  <- {label}")
    return pdu[1:]


async def main():
    global rx
    rx = asyncio.Queue()
    net = mesh.load()
    print(f"network store: {mesh.STORE}")
    print(f"  network id {mesh.k3(bytes.fromhex(net['netkey'])).hex()}"
          f"  iv_index {net['iv_index']}   (netkey not printed)")
    print(f"  {len(net['nodes'])} node(s) already provisioned\n")

    print("finding unprovisioned node...")
    # Nearest, not first-heard: a node claimed at -90 dBm provisions over the
    # advertising bearer just fine and is then unreachable over GATT, which
    # surfaces much later as an unexplained connect timeout.
    dev = await ble.find_unprovisioned()
    if not dev:
        print("no unprovisioned node found.")
        return
    if DRY:
        print("--dry-run: stopping before any state change.")
        return

    addr = net["next_addr"]
    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        print(f"connected, ATT MTU {mtu}, assigning unicast 0x{addr:04x}\n")
        await cli.start_notify(DATA_OUT, on_notify)

        # --- invite / capabilities ---
        invite_params = bytes([0x00])
        print("  -> Invite")
        await send(cli, bytes([T_INVITE]) + invite_params, mtu)
        caps = await expect(T_CAPS, "Capabilities")

        # --- start: algo 0, no oob pubkey, No OOB auth ---
        start_params = bytes([0x00, 0x00, 0x00, 0x00, 0x00])
        print("  -> Start (No OOB)")
        await send(cli, bytes([T_START]) + start_params, mtu)

        # --- ECDH ---
        priv = ec.generate_private_key(ec.SECP256R1())
        n = priv.public_key().public_numbers()
        pub_p = n.x.to_bytes(32, "big") + n.y.to_bytes(32, "big")
        print("  -> PublicKey")
        await send(cli, bytes([T_PUBKEY]) + pub_p, mtu)
        pub_d = await expect(T_PUBKEY, "PublicKey (device)")

        peer = ec.EllipticCurvePublicNumbers(
            int.from_bytes(pub_d[:32], "big"),
            int.from_bytes(pub_d[32:64], "big"),
            ec.SECP256R1()).public_key()
        secret = priv.exchange(ec.ECDH(), peer)

        # --- confirmation ---
        inputs = invite_params + caps + start_params + pub_p + pub_d
        assert len(inputs) == 145, len(inputs)
        conf_salt = mesh.s1(inputs)
        conf_key = mesh.k1(secret, conf_salt, b"prck")
        auth = b"\x00" * 16                      # No OOB
        rand_p = os.urandom(16)
        conf_p = mesh.aes_cmac(conf_key, rand_p + auth)
        print("  -> Confirmation")
        await send(cli, bytes([T_CONFIRM]) + conf_p, mtu)
        conf_d = await expect(T_CONFIRM, "Confirmation (device)")

        print("  -> Random")
        await send(cli, bytes([T_RANDOM]) + rand_p, mtu)
        rand_d = await expect(T_RANDOM, "Random (device)")

        if mesh.aes_cmac(conf_key, rand_d + auth) != conf_d:
            raise RuntimeError("device confirmation MISMATCH -- aborting")
        print("  ++ device confirmation verified\n")

        # --- provisioning data ---
        prov_salt = mesh.s1(conf_salt + rand_p + rand_d)
        session_key = mesh.k1(secret, prov_salt, b"prsk")
        session_nonce = mesh.k1(secret, prov_salt, b"prsn")[3:]
        devkey = mesh.k1(secret, prov_salt, b"prdk")

        data = (bytes.fromhex(net["netkey"])
                + net["key_index"].to_bytes(2, "big")
                + bytes([net["flags"]])
                + net["iv_index"].to_bytes(4, "big")
                + addr.to_bytes(2, "big"))
        assert len(data) == 25
        enc = mesh.ccm_encrypt(session_key, session_nonce, data, tag=8)
        print("  -> Data (encrypted)")
        await send(cli, bytes([T_DATA]) + enc, mtu)
        await expect(T_COMPLETE, "Complete")

        net["nodes"][f"0x{addr:04x}"] = {
            "ble_address": dev.address,
            "name": (dev.name or "").strip(),
            "devkey": devkey.hex(),
            "unicast": addr,
            "elements": caps[0],
        }
        net["next_addr"] = addr + caps[0]
        mesh.save(net)

        print(f"\nPROVISIONED. unicast 0x{addr:04x}, {caps[0]} element(s)")
        print(f"  devkey  {devkey.hex()}")
        print(f"  net id  {mesh.k3(bytes.fromhex(net['netkey'])).hex()}")
        print(f"  saved to {mesh.STORE}")
        await cli.stop_notify(DATA_OUT)


if __name__ == "__main__":
    asyncio.run(main())
