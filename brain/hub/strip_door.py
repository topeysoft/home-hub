# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# OUR OWN DOOR ONTO A STRIP, FROM THIS SIDE.
#
# A strip we make offers two ways in and the household is never asked which (design/strip/Both.dc.html).
# Matter's is for anybody; this one is ours, and it is the only one that can ask the two questions Matter
# has no words for -- which order the colors come out in, and how far the strip goes -- and the only one
# that can tell the strip where we are.
#
# The protocol underneath is Espressif's protocomm with SRP6a, vendored in brain/vendor/esp_prov, because
# writing an SRP6a client to talk to our own SRP6a is not work worth doing twice. What is ours is this
# file: finding a strip by the service UUID rather than by a name, and the `hub` step at the end.
#
# THE PASSWORD IS THE RHYTHM (design/strip/PopLight.dc.html). A strip mints four counts of one to six each
# time it is plugged in and flashes them; the household taps what it sees and those four digits are the
# proof of possession. Nothing is printed on the strip and nothing is derived from its chip, so there is
# nothing to read off a unit and nothing to leak out of a factory.
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vendor'))

from esp_prov.prov import wifi_prov            # noqa: E402
from esp_prov.security.security2 import Security2, security_state  # noqa: E402
from esp_prov.transport.transport import Transport  # noqa: E402

# The service a strip offers us, and the endpoints on it. The sixteen-bit part of each characteristic
# sits at byte 12 of the service UUID, which is protocomm's convention and what the firmware writes.
SERVICE_UUID = '1775244d-6b43-439b-877c-060f2d9bed07'
ENDPOINTS = {
    'prov-session': 0xFF51,
    'prov-config': 0xFF52,
    'proto-ver': 0xFF53,
    'hub': 0xFF54,
}
# Fixed and public; the rhythm is the whole secret.
USERNAME = 'wifiprov'


def _chrc_uuid(ep: str) -> str:
    return f'{SERVICE_UUID[:4]}{ENDPOINTS[ep]:04x}{SERVICE_UUID[8:]}'


class _Bleak(Transport):
    """protocomm over one BLE connection, talking to characteristics we address by UUID.

    Espressif's own Transport_BLE cannot be used unchanged for two reasons, both about assumptions that
    do not hold here: it finds a device by advertised NAME, and our scan response has barely room for
    one, so the UUID is the identifier; and it derives characteristic UUIDs by masking the endpoint id
    against the service UUID, which is a no-op for the all-ff service they assume and mangles ours.
    """

    def __init__(self, client):
        self.client = client

    async def send_data(self, ep_name, data):
        await self.client.write_gatt_char(_chrc_uuid(ep_name), bytearray(data.encode('latin-1')), response=True)
        return (await self.client.read_gatt_char(_chrc_uuid(ep_name))).decode('latin-1')

    async def send_session_data(self, data):
        return await self.send_data('prov-session', data)

    async def send_config_data(self, data):
        return await self.send_data('prov-config', data)

    async def disconnect(self):
        pass


async def find(timeout: float = 8.0):
    """Every strip within earshot that is waiting to be set up, newest advertisement first."""
    from bleak import BleakScanner
    seen = {}

    def note(device, adv):
        if SERVICE_UUID in [u.lower() for u in (adv.service_uuids or [])]:
            seen[device.address] = (device, adv)

    scanner = BleakScanner(note)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    return [{'address': a, 'name': d.name, 'rssi': adv.rssi} for a, (d, adv) in seen.items()]


async def adopt(address: str, rhythm: str, ssid: str, passphrase: str, hub: dict | None = None) -> None:
    """Take a strip: prove the rhythm, hand over the Wi-Fi, then say where we are.

    `rhythm` is the four counts the household read off the light, as digits. `hub` is what the strip
    needs to find us again after it reboots -- mhost, and the broker credentials if there are any.
    Raises on any step, because a half-adopted strip is worse than one that never started.
    """
    from bleak import BleakClient
    _tolerate_corebluetooth()

    security = Security2(sec_patch_ver=1, username=USERNAME, password=rhythm, verbose=False)
    async with BleakClient(address, timeout=20.0) as client:
        transport = _Bleak(client)

        # The handshake, until protocomm says there is nothing left to send. A wrong rhythm fails
        # here, inside SRP6a, and ends the session: there is no offline guessing at four digits.
        response = None
        while True:
            request = security.security_session(response)
            if request is None:
                break
            response = await transport.send_session_data(request)
        if security.session_state != security_state.FINISHED:
            raise RuntimeError('the strip did not accept that rhythm')

        sent = await transport.send_config_data(wifi_prov.config_set_config_request(security, ssid, passphrase))
        if wifi_prov.config_set_config_response(security, sent) != 0:
            raise RuntimeError('the strip would not take those Wi-Fi credentials')

        applied = await transport.send_config_data(wifi_prov.config_apply_config_request(security))
        if wifi_prov.config_apply_config_response(security, applied) != 0:
            raise RuntimeError('the strip would not apply those Wi-Fi credentials')

        # WHERE WE ARE, IN THE SESSION THAT IS ALREADY OPEN. This is the one moment it is safe to say:
        # a session the strip authenticated, with somebody standing in the room. A strip that finishes
        # without it is a Matter light and nothing more (docs/strip.md item 2a).
        if hub:
            body = ''.join(f'{k}={v}\n' for k, v in hub.items() if v is not None)
            answer = await transport.send_data('hub', security.encrypt_data(body.encode('latin-1')).decode('latin-1'))
            said = security.decrypt_data(answer.encode('latin-1')).decode('latin-1')
            if said != 'ok':
                raise RuntimeError(f'the strip answered "{said}" when told where we are')


def _tolerate_corebluetooth() -> None:
    """macOS refuses descriptor discovery on characteristics it reserves, and bleak does that discovery
    for every characteristic while connecting, so one refusal loses the whole table and nothing can be
    addressed. The hub runs on Linux, where this does not arise; this is here so a bench on a Mac is not
    a dead end, and it does nothing anywhere else."""
    if sys.platform != 'darwin':
        return
    from bleak.backends.corebluetooth.PeripheralDelegate import PeripheralDelegate
    if getattr(PeripheralDelegate, '_hub_patched', False):
        return
    original = PeripheralDelegate.discover_descriptors

    async def lenient(self, characteristic):
        try:
            return await original(self, characteristic)
        except Exception:
            return []

    PeripheralDelegate.discover_descriptors = lenient
    PeripheralDelegate._hub_patched = True
