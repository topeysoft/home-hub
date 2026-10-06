# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Talking to a bridge puck over its cable, without a puck or a cable.

hub/puck_cable.py is what the hub says to a puck plugged into it, and what the bench says to one on a
desk. The link is a USB serial port shared with the firmware's own log, and it tears the odd line, so
most of what is held here is about not believing one reading: an answer is picked out of the noise, a
torn hello is asked again, a status is taken only whole, and a set is repeated until its own `ok`
comes back. And the one rule that makes a puck older than its hub still adoptable: `err what` is a
version gap, `err bad` is a fault (docs/puck-updates.md).

The fake clock moves a second every time it is read, so every wait in the module runs out at once.
"""
import hashlib, io, json, pathlib, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

from hub import puck_cable as pc

# The Mesh Profile 1.0.1 sample keys (8.1.1, 8.1.2): a test never holds a real house's.
NETKEY = "7dd7364cd842ad18c17c2b820c84c3d6"
APPKEY = "63964771734fbd76e3b40519d1d94a48"


class Clock:
    """time, as puck_cable sees it: a second passes every time somebody looks, and sleeping is free."""
    def __init__(self): self.now = 0.0
    def time(self): self.now += 1.0; return self.now
    def sleep(self, _s): pass


class Wire:
    """A serial port with a puck on the far side. `answer` maps the line written to the lines the puck
    sends back, log noise and all; a list of answers for one verb is used up one per asking."""
    def __init__(self, answer):
        self.answer, self.sent, self.buf, self.closed = answer, [], b"", False

    def write(self, data):
        line = data.decode().strip(); self.sent.append(line)
        got = self.answer(line)
        for out in ([got] if isinstance(got, str) else (got or [])):
            self.buf += (out + "\n").encode()

    def flush(self): pass
    def reset_input_buffer(self): self.buf = b""

    def read(self, _n):
        d, self.buf = self.buf, b""
        return d

    def close(self): self.closed = True


def script(**verbs):
    """A puck that answers each verb from a queue: the last answer repeats once the queue runs out."""
    queues = {k: list(v) if isinstance(v, list) else [v] for k, v in verbs.items()}
    def answer(line):
        w = line.split()
        verb = w[1] if w[0] == "set" else w[0]
        q = queues.get(verb)
        if not q: return None
        return q.pop(0) if len(q) > 1 else q[0]
    return answer


class Case(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        p = mock.patch.object(pc, "time", self.clock); p.start(); self.addCleanup(p.stop)

    def puck(self, **verbs):
        self.wire = Wire(script(**verbs))
        with mock.patch.object(pc, "open_port", return_value=self.wire):
            return pc.Puck("/dev/fake")


class OpeningThePort(Case):
    class Serial:
        fails = 0
        def __init__(self): self.opened = False
        def open(self):
            if OpeningThePort.Serial.fails:
                OpeningThePort.Serial.fails -= 1
                raise pc.serial.SerialException("busy")
            assert self.dtr is False and self.rts is False, "DTR and RTS are held low before opening, or the board resets"
            self.opened = True

    def test_it_keeps_trying_while_the_board_re_enumerates(self):
        self.Serial.fails = 3
        with mock.patch.object(pc.serial, "Serial", self.Serial):
            s = pc.open_port("/dev/fake")
        self.assertTrue(s.opened)
        self.assertEqual((s.port, s.baudrate), ("/dev/fake", 115200))

    def test_it_gives_up_with_the_ports_own_reason(self):
        self.Serial.fails = 5
        with mock.patch.object(pc.serial, "Serial", self.Serial), self.assertRaises(pc.serial.SerialException):
            pc.open_port("/dev/fake", tries=3)

    def test_letting_go_of_a_port_that_is_already_gone_is_quiet(self):
        p = self.puck()
        p.s.close = mock.Mock(side_effect=OSError("gone"))
        p.close()


class Asking(Case):
    def test_the_answer_is_picked_out_of_the_firmwares_log(self):
        p = self.puck(status="I (1234) wifi: connected\nmesh: beacon\nstatus wifi=up")
        self.assertEqual(p.ask("status"), "status wifi=up")

    def test_silence_is_a_timeout_naming_the_verb(self):
        p = self.puck()
        with self.assertRaisesRegex(TimeoutError, "'status'"):
            p.ask("status now")

    def test_two_lines_in_one_read_are_both_seen(self):
        p = self.puck(hello="boot: ok\nbridge c8ebba 0.6.0 set")
        self.assertEqual(p.ask("hello"), "bridge c8ebba 0.6.0 set")


class Hello(Case):
    def test_a_torn_hello_is_asked_again_not_trusted(self):
        p = self.puck(hello=["bridge c8eb", "bridge c8ebba 0.6.0 blank"])
        self.assertEqual(p.hello(), {"chip": "c8ebba", "fw": "0.6.0", "state": "blank"})
        self.assertEqual(self.wire.sent, ["hello", "hello"])

    def test_a_puck_that_never_says_it_cleanly_is_reported_with_what_it_did_say(self):
        p = self.puck(hello="bridge c8ebba")
        with self.assertRaisesRegex(RuntimeError, "last: 'bridge c8ebba'"):
            p.hello(patience=6)

    def test_a_puck_still_in_its_bootloader_is_waited_for(self):
        p = self.puck()
        with self.assertRaisesRegex(RuntimeError, "no clean hello"):
            p.hello(patience=6)


class Status(Case):
    def test_only_a_whole_status_is_taken(self):
        p = self.puck(status=["status wifi=up mqtt=up", "status wifi=192.168.1.30 mqtt=up rssi=-61 sw=2 light=heard"])
        self.assertEqual(p.status()["rssi"], "-61")

    def test_a_puck_without_the_mesh_has_no_rssi_or_sw_and_is_still_whole(self):
        p = self.puck(status="status wifi=192.168.1.30 mqtt=up light=heard")
        self.assertEqual(p.status(), {"wifi": "192.168.1.30", "mqtt": "up", "light": "heard"})

    def test_a_line_torn_before_its_last_field_is_asked_again(self):
        p = self.puck(status=["status wifi=192.168.1.30 mqtt=up rssi=-61", "status wifi=192.168.1.30 mqtt=up rssi=-61 sw=2 light=heard"])
        self.assertEqual(p.status()["light"], "heard")
        self.assertEqual(self.wire.sent, ["status", "status"])

    def test_never_whole_is_an_error(self):
        p = self.puck(status="status wifi=up")
        with self.assertRaisesRegex(RuntimeError, "no clean status"):
            p.status()


class Setting(Case):
    def test_a_value_that_took(self):
        p = self.puck(wifi="ok wifi")
        self.assertTrue(p.set("wifi", pc.hx("Upstairs"), pc.hx("pass")))
        self.assertEqual(self.wire.sent, [f"set wifi {pc.hx('Upstairs')} {pc.hx('pass')}"])

    def test_a_torn_ok_is_set_again(self):
        p = self.puck(base=["ok ba", "ok base"])
        self.assertTrue(p.set("base", pc.hx("mesh")))
        self.assertEqual(len(self.wire.sent), 2)

    def test_a_verb_too_new_for_this_puck_is_a_version_gap_when_it_is_optional(self):
        p = self.puck(name="err what")
        self.assertFalse(p.set("name", pc.hx("hub"), required=False))

    def test_a_verb_too_new_is_still_a_failure_when_it_is_required(self):
        p = self.puck(wifi="err what")
        with self.assertRaisesRegex(RuntimeError, "refused wifi"):
            p.set("wifi", "00", "00")

    def test_a_bad_argument_is_a_fault_at_any_version(self):
        p = self.puck(name="err bad")
        with self.assertRaisesRegex(RuntimeError, "err bad"):
            p.set("name", "zz", required=False)

    def test_no_answer_at_all_is_an_error(self):
        p = self.puck()
        with self.assertRaisesRegex(RuntimeError, "no clean answer to set label"):
            p.set("label", pc.hx("Hall"))


class ApplyAndWipe(Case):
    def test_apply_lets_go_of_the_port_for_the_restart(self):
        p = self.puck(apply="ok apply")
        p.apply()
        self.assertTrue(self.wire.closed)

    def test_wipe_lets_go_of_the_port_too(self):
        p = self.puck(wipe="ok wipe")
        p.wipe()
        self.assertTrue(self.wire.closed)

    def test_a_refusal_says_so(self):
        for verb in ("apply", "wipe"):
            p = self.puck(**{verb: "err busy"})
            with self.assertRaisesRegex(RuntimeError, f"refused {verb}"):
                getattr(p, verb)()


HEADER = f"""
#define WIFI_SSID "Upstairs"
#define WIFI_PASS "correct horse"
#define MQTT_HOST "hub.local"
#define MQTT_PORT 1883
#define MQTT_USER "puck"
#define MQTT_PASS "s3cret"
#define MQTT_BASE "mesh"
#define DEVICE_LABEL "Hall"
#define IV_INDEX 7
static const uint8_t NET_KEY[16] = {{ {", ".join("0x" + NETKEY[i:i + 2] for i in range(0, 32, 2))} }};
static const uint8_t APP_KEY[16] = {{ {", ".join("0x" + APPKEY[i:i + 2].upper() for i in range(0, 32, 2))} }};
"""


class ADeskHeader(unittest.TestCase):
    def test_a_puck_is_handed_exactly_what_it_was_compiled_with(self):
        with tempfile.NamedTemporaryFile("w", suffix=".h") as f:
            f.write(HEADER); f.flush()
            h = pc.from_header(f.name)
        self.assertEqual(h, {"WIFI_SSID": "Upstairs", "WIFI_PASS": "correct horse", "MQTT_HOST": "hub.local",
                             "MQTT_USER": "puck", "MQTT_PASS": "s3cret", "MQTT_BASE": "mesh", "DEVICE_LABEL": "Hall",
                             "MQTT_PORT": "1883", "IV_INDEX": "7", "NET_KEY": NETKEY, "APP_KEY": APPKEY})

    def test_a_header_with_nothing_in_it_gives_nothing(self):
        with tempfile.NamedTemporaryFile("w", suffix=".h") as f:
            f.write("// empty\n"); f.flush()
            self.assertEqual(pc.from_header(f.name), {})


def tree(root: pathlib.Path, nvs="0x9000, 0x5000", image=b"\x00" * pc.NVS_START + b"\xff" * (pc.NVS_END - pc.NVS_START) + b"APP",
         sha=None, fw="0.7.0"):
    """The two files upgrade reads, laid out under a fake repository root."""
    (root / "puck").mkdir(parents=True)
    rows = "# Name, Type, SubType, Offset, Size\n" + (f"nvs, data, nvs, {nvs}\n" if nvs else "") + "app0, app, ota_0, 0x10000, 0x300000\n"
    (root / "puck/partitions-ota.csv").write_text(rows)
    (root / "releases/bridge").mkdir(parents=True)
    (root / "releases/bridge/esp32s3-ship.bin").write_bytes(image)
    meta = {"fw": fw, "sha256": sha or hashlib.sha256(image).hexdigest()}
    (root / "releases/bridge/esp32s3-ship.json").write_text(json.dumps(meta))
    return image


class Upgrading(Case):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        p = mock.patch.object(pc, "ROOT", self.root); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(pc, "_esptool", return_value="esptool.py"); p.start(); self.addCleanup(p.stop)

    def run_upgrade(self, before, after):
        """`before` and `after` are what the puck says to hello on either side of the flash; None is silence."""
        flashed = []
        def puck(_port):
            said = after if flashed else before
            if said is None: raise TimeoutError("deaf")
            return mock.Mock(hello=mock.Mock(return_value={"chip": "c8ebba", "fw": "0.7.0-d1", "state": said}))
        out = io.StringIO()
        with mock.patch.object(pc, "Puck", side_effect=puck), \
                mock.patch.object(pc.subprocess, "run", side_effect=lambda *a, **k: flashed.append(a)) as run, redirect_stdout(out):
            pc.upgrade("/dev/fake")
        return run, out.getvalue()

    def test_the_image_goes_down_in_two_pieces_around_nvs(self):
        tree(self.root)
        run, out = self.run_upgrade("set", "set")
        argv = run.call_args.args[0]
        head, tail = pathlib.Path(argv[argv.index("0x0") + 1]), argv[argv.index(hex(pc.NVS_END)) + 1]
        self.assertNotIn(hex(pc.NVS_START), argv, "nothing is written at nvs")
        self.assertIn("still knows who it is", out)
        self.assertEqual(head.name, "head.bin"); self.assertTrue(tail.endswith("tail.bin"))

    def test_a_puck_that_comes_back_blank_stops_the_line(self):
        tree(self.root)
        with self.assertRaisesRegex(SystemExit, "came back blank"):
            self.run_upgrade("set", "blank")

    def test_a_silent_puck_is_flashed_anyway_and_said_so(self):
        tree(self.root)
        _, out = self.run_upgrade(None, "blank")
        self.assertIn("flashing anyway", out)

    def test_an_image_that_does_not_match_its_record_is_refused(self):
        tree(self.root, sha="0" * 64)
        with self.assertRaisesRegex(SystemExit, "does not match"):
            pc.upgrade("/dev/fake")

    def test_a_moved_nvs_is_refused_before_anything_is_flashed(self):
        tree(self.root, nvs="0xa000, 0x5000")
        with self.assertRaisesRegex(SystemExit, "would wipe every puck's identity"):
            pc.upgrade("/dev/fake")

    def test_a_puck_is_never_upgraded_to_another_kind(self):
        """A switch puck given the public image keeps its keys and loses the code that used them."""
        tree(self.root)                                  # the tree's image is 0.7.0, the plain kind
        def puck(_port):
            return mock.Mock(hello=mock.Mock(return_value={"chip": "c8ebba", "fw": "0.6.0", "state": "set"}))
        with mock.patch.object(pc, "Puck", side_effect=puck), mock.patch.object(pc.subprocess, "run") as run, \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(SystemExit, "pass --image"):
            pc.upgrade("/dev/fake")
        run.assert_not_called()

    def test_another_folder_of_its_own_kind_is_taken(self):
        own = self.root / "puck-firmware"; own.mkdir()
        image = b"\x00" * pc.NVS_END + b"APP"
        (own / "esp32s3-ship.bin").write_bytes(image)
        (own / "esp32s3-ship.json").write_text(json.dumps({"fw": "0.7.0+mesh", "sha256": hashlib.sha256(image).hexdigest()}))
        tree(self.root)
        flashed = []
        def puck(_port):
            return mock.Mock(hello=mock.Mock(return_value={"chip": "c8ebba", "fw": "0.6.0" if not flashed else "0.7.0+mesh", "state": "set"}))
        with mock.patch.object(pc, "Puck", side_effect=puck), \
                mock.patch.object(pc.subprocess, "run", side_effect=lambda *a, **k: flashed.append(a)), redirect_stdout(io.StringIO()):
            pc.upgrade("/dev/fake", str(own))
        self.assertEqual(len(flashed), 1)

    def test_a_blank_board_takes_either_kind(self):
        tree(self.root)
        run, _ = self.run_upgrade("blank", "blank")
        run.assert_called_once()

    def test_a_table_with_no_nvs_is_refused(self):
        tree(self.root, nvs=None)
        with self.assertRaisesRegex(SystemExit, "no nvs row"):
            pc.upgrade("/dev/fake")

    def test_a_puck_that_never_comes_back_is_reported(self):
        tree(self.root)
        def puck(_port): raise TimeoutError("deaf")
        with mock.patch.object(pc, "Puck", side_effect=puck), mock.patch.object(pc.subprocess, "run"), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(SystemExit, "did not come back"):
            pc.upgrade("/dev/fake")


class FindingEsptool(unittest.TestCase):
    def test_no_platformio_means_no_flashing(self):
        with mock.patch.object(pc.glob, "glob", return_value=[]), self.assertRaisesRegex(SystemExit, "no esptool"):
            pc._esptool()

    def test_the_one_platformio_installed_is_used(self):
        with mock.patch.object(pc.glob, "glob", return_value=["/p/esptool.py"]):
            self.assertEqual(pc._esptool(), "/p/esptool.py")


class TheCommandLine(Case):
    def main(self, *argv, **verbs):
        verbs = {"hello": "bridge c8ebba 0.6.0 blank", **verbs}
        self.wire = Wire(script(**verbs))
        out = io.StringIO()
        with mock.patch.object(pc, "open_port", return_value=self.wire), mock.patch.object(sys, "argv", ["puck_cable.py", "/dev/fake", *argv]), \
                redirect_stdout(out):
            pc.main()
        return out.getvalue()

    def test_write_sends_each_value_in_order_and_leaves_the_restart_when_asked(self):
        ok = {v: f"ok {v}" for v in ("wifi", "name", "wifi2", "mqtt", "keys", "base", "label")}
        out = self.main("write", "--wifi", "Upstairs", "pw", "--name", "hub", "--wifi2", "Downstairs", "pw2",
                        "--mqtt", "hub.local", "1883", "puck", "pw3", "--keys", NETKEY, APPKEY, "7",
                        "--base", "mesh", "--label", "Hall", "--no-apply", **ok)
        verbs = [line.split()[1] for line in self.wire.sent if line.startswith("set ")]
        self.assertEqual(verbs, ["wifi", "name", "wifi2", "mqtt", "keys", "base", "label"])
        self.assertIn("not applied", out)
        self.assertNotIn(NETKEY, out, "a key is never printed whole")

    def test_write_from_a_header_then_waits_for_the_puck_to_come_back(self):
        ok = {v: f"ok {v}" for v in ("wifi", "mqtt", "keys", "base", "label", "apply")}
        with tempfile.NamedTemporaryFile("w", suffix=".h") as f:
            f.write(HEADER); f.flush()
            out = self.main("write", "--from", f.name, **ok)
        self.assertIn(f"set keys {NETKEY} {APPKEY} 7", self.wire.sent)
        self.assertIn("back: puck c8ebba", out)

    def test_an_old_puck_is_told_its_name_is_skipped_not_failed(self):
        out = self.main("write", "--wifi", "Upstairs", "pw", "--name", "hub", "--no-apply", wifi="ok wifi", name="err what")
        self.assertIn("too old to know it (0.6.0)", out)

    def test_write_with_nothing_to_write_says_so(self):
        with self.assertRaisesRegex(SystemExit, "nothing to write"):
            self.main("write")

    def test_hello_status_and_wipe(self):
        self.assertIn("'chip': 'c8ebba'", self.main("hello"))
        self.assertIn("'sw': '2'", self.main("status", status="status wifi=up mqtt=up rssi=-60 sw=2 light=heard"))
        self.assertIn("wiping", self.main("wipe", wipe="ok wipe"))

    def test_upgrade_is_handed_the_port(self):
        with mock.patch.object(pc, "upgrade") as up:
            self.main("upgrade")
        up.assert_called_once_with("/dev/fake", None)


if __name__ == "__main__":
    unittest.main()
