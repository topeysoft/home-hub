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
# THE PROOF IS A PRESS (design/door/PressIt.dc.html, design/strip/Press.dc.html). The household presses
# the button on the controller of the thing they have just unpacked, and that is the whole handshake:
# nothing printed, nothing derived from a chip, nothing to count. THE GATE IS ON THE STRIP, not here --
# this client can open a session and get exactly as far as the Wi-Fi question, where the strip refuses
# it until somebody in the room has touched the object. So the password below is fixed and public on
# purpose; it is not what makes this safe and it is not pretending to be.
#
# AND WHEN NOBODY CAN REACH THE BUTTON, one rung down (design/strip/ReachRhythm.dc.html): the strip
# mints four counts of one to six, flashes them, and reopens its door with an SRP6a verifier made from
# them. That is PopLight, which shipped as what everybody got and was demoted the same day -- counting
# flashes is a chore, and a proof made of light only works on something two metres long.
import asyncio
import os
import sys
import time

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
    'press': 0xFF55,
}
USERNAME = 'wifiprov'
# What we say when the strip is waiting for a press. Public, and it has to be: on this rung there is no
# secret at all, which is the point of choosing it. On the rung below, the rhythm takes its place and is
# a real one.
OPEN_SESAME = 'press'

# HOW LONG SOMEBODY HAS TO WALK TO THE THING AND PRESS IT. Two minutes is the walk across a house and
# back, and it is also the window an attacker in radio range would have to be racing in -- the residual
# risk this rung accepts, written down rather than implied. The poll is what the panel's own "waiting"
# line is made of, so it is fast enough to feel like an answer and slow enough not to hold the link busy.
PRESS_WAIT = 120.0
PRESS_POLL = 0.7
# AND WHEN THE STRIP CAN RING, HARDLY AT ALL (design/ears/Tell.dc.html). A strip that notifies on the
# press is asked once, then again when it rings -- and every RING_POLL seconds in case a ring is lost,
# because a household standing at a strip that has gone quiet is the one failure this must not have.
# A hundred and seventy asks across a courier's radio become a dozen at most, which is also what
# keeps a bridge puck inside its buffers (docs/strip.md item 39).
RING_POLL = 10.0


class NotPressed(Exception):
    """Nobody pressed it. Not a radio failure and it must never be reported as one: the household is
    standing in the right place and has simply not touched the thing yet."""


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
        self._rung = asyncio.Event()

    async def listen_for_ring(self) -> bool:
        """Ask to be rung when the button is pressed. False from a strip too old to ring, which is not
        an error: it is simply asked the old way."""
        try:
            await self.client.start_notify(_chrc_uuid('press'), lambda *_: self._rung.set())
            return True
        except Exception:                                        # noqa: BLE001 -- no notify, no ring
            return False

    async def wait_for_ring(self):
        await self._rung.wait()
        self._rung.clear()

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


async def adopt(address: str, ssid: str, passphrase: str, hub: dict | None = None,
                rhythm: str = '', on_pressed=None, out_of_reach: "asyncio.Event | None" = None,
                press_wait: float = PRESS_WAIT, transport: "Transport | None" = None) -> str:
    """Take a strip: wait for the press, hand over the Wi-Fi, then say where we are.

    `rhythm`, when there is one, is the four counts the household read off the light -- the rung below
    the press, and then it is the SRP6a password and there is nothing to wait for. `hub` is what the
    strip needs to find us again after it reboots. `on_pressed` is called the moment the strip says it
    was touched, so the wall can stop saying it is waiting. `out_of_reach` is the household saying they
    cannot reach the button; setting it asks the strip for a rhythm instead and returns 'rhythm'.

    `transport` is for something that is not our own radio -- a courier that carries the bytes to a
    strip this machine cannot hear (docs/strip.md item 38). Nothing below changes when there is one:
    the session is still opened here and closed at the strip, and the press gate is still on the strip.

    Returns 'done', or 'rhythm' if the strip was asked to drop a rung. Raises on any step, because a
    half-adopted strip is worse than one that never started.
    """
    security = Security2(sec_patch_ver=1, username=USERNAME, password=rhythm or OPEN_SESAME, verbose=False)
    if transport is not None:
        return await _adopt_over(transport, security, ssid, passphrase, hub, rhythm,
                                 on_pressed, out_of_reach, press_wait)

    from bleak import BleakClient
    _tolerate_corebluetooth()
    async with BleakClient(address, timeout=20.0) as client:
        return await _adopt_over(_Bleak(client), security, ssid, passphrase, hub, rhythm,
                                 on_pressed, out_of_reach, press_wait)


async def _adopt_over(transport, security, ssid, passphrase, hub, rhythm,
                      on_pressed, out_of_reach, press_wait) -> str:
    """Everything an adoption is, once there is something to say it down. Split out from `adopt` so
    that the same steps run whether the bytes go over our own radio or through a courier."""
    # The handshake, until protocomm says there is nothing left to send. A wrong rhythm fails
    # here, inside SRP6a, and ends the session: there is no offline guessing at four digits.
    # With no rhythm the password is public, so this proves nothing and is not meant to -- it is
    # the encrypted channel the rest of the conversation needs, and the strip's own gate is what
    # the Wi-Fi is actually waiting on.
    response = None
    while True:
        request = security.security_session(response)
        if request is None:
            break
        response = await transport.send_session_data(request)
    if security.session_state != security_state.FINISHED:
        raise RuntimeError('the strip did not accept that rhythm')

    if not rhythm and await _wait_for_the_press(transport, security, on_pressed,
                                               out_of_reach, press_wait) == 'rhythm':
        return 'rhythm'

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
    return 'done'


async def _ask(transport, security, question: str) -> str:
    """One question on the `press` endpoint, inside the session. The endpoint answers 'waiting' until
    somebody has touched the strip, 'pressed' once they have, and 'ok' when asked for a rhythm."""
    answer = await transport.send_data('press', security.encrypt_data(question.encode('latin-1')).decode('latin-1'))
    return security.decrypt_data(answer.encode('latin-1')).decode('latin-1')


async def _wait_for_the_press(transport, security, on_pressed, out_of_reach, wait: float) -> str:
    """Hold, politely, until somebody presses the button on the thing.

    NOTHING OF THE HOUSE'S HAS MOVED YET and that is the whole shape of this rung: the session is open,
    the strip is lit, and the credentials are still here. The only two ways out are a press and the
    household saying they cannot reach it.

    The ring only ever says "ask now". The answer still comes back inside the session, the ordinary
    way, so a strip that rings and a strip that does not are told apart by nothing but how often they
    are asked."""
    rings = await _listen(transport)
    every = RING_POLL if rings else PRESS_POLL
    until = time.monotonic() + wait
    while True:
        if out_of_reach is not None and out_of_reach.is_set():
            await _ask(transport, security, 'rhythm')
            return 'rhythm'
        said = await _ask(transport, security, '?')
        if said == 'pressed':
            if on_pressed:
                on_pressed()
            return 'pressed'
        if said != 'waiting':
            raise RuntimeError(f'the strip answered "{said}" when asked about the press')
        left = until - time.monotonic()
        if left <= 0:
            raise NotPressed('nobody pressed the button on the strip')
        await _rest(transport if rings else None, out_of_reach, min(every, left))


async def _listen(transport) -> bool:
    listen = getattr(transport, 'listen_for_ring', None)
    return bool(listen and await listen())


async def _rest(transport, out_of_reach, seconds: float):
    """The pause between asks: the poll interval, cut short by a ring, or by somebody saying they
    cannot reach the button -- which must answer at once however long the poll has become."""
    waits = [asyncio.ensure_future(asyncio.sleep(seconds))]
    if transport is not None:
        waits.append(asyncio.ensure_future(transport.wait_for_ring()))
    if out_of_reach is not None:
        waits.append(asyncio.ensure_future(out_of_reach.wait()))
    try:
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for w in waits:
            w.cancel()


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
