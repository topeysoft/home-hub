# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The operator's tool says what it did, in a sentence, and fails in one too."""
import tempfile, unittest
from pathlib import Path

from cli import run
from registry import Registry


class Operator(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.r = Registry(Path(self.dir.name) / "houses.db")
        self.said = []

    def tearDown(self):
        self.r.db.close(); self.dir.cleanup()

    def say(self, *argv):
        self.said.clear()
        code = run(list(argv), self.r, out=self.said.append)
        return code, "\n".join(self.said)

    def test_grant_then_stop_then_release(self):
        self.r.claim("temi")
        self.assertEqual(self.say("grant", "temi", "2099-10-01", "Temi,", "by", "hand"), (0, "temi is carried until 2099-10-01."))
        code, listed = self.say("list")
        self.assertIn("carried until 2099-10-01", listed); self.assertIn("Temi, by hand", listed)
        self.assertTrue(self.r.status("temi")["carried"])
        self.assertEqual(self.say("stop", "temi")[0], 0)
        self.assertFalse(self.r.status("temi")["carried"]); self.assertTrue(self.r.taken("temi"))
        self.assertEqual(self.say("release", "temi")[0], 0)
        self.assertFalse(self.r.taken("temi"))

    def test_a_house_that_is_not_there_is_named(self):
        self.assertEqual(self.say("grant", "nobody", "2099-01-01"), (1, "No house called nobody."))

    def test_rotate_prints_the_new_secret_and_nothing_else(self):
        self.r.claim("temi")
        code, secret = self.say("rotate", "temi")
        self.assertEqual(code, 0); self.assertTrue(self.r.holder("temi", secret))

    def test_nonsense_gets_the_usage(self):
        self.assertEqual(self.say()[0], 2)
        self.assertEqual(self.say("grant", "temi")[0], 2)
        self.assertEqual(self.say("grant", "temi", "next tuesday")[0], 2)


if __name__ == "__main__":
    unittest.main()

    def test_invite_list_and_take_back(self):
        code, said = self.say("invite", "2099-10-01", "a", "tester")
        self.assertEqual(code, 0)
        made = said.splitlines()[0]
        self.assertIn("only time it is shown", said)
        self.assertIn("unused, good until", self.say("invites")[1])
        self.r.claim("desk", invite=made)
        listed = self.say("invites")[1]
        self.assertIn("used by desk", listed); self.assertIn("a tester", listed)
        self.assertEqual(self.say("uninvite", made[-4:])[0], 1)          # used: nothing to take back
        self.assertEqual(self.say("invite", "2001-01-01"), (2, "That date has passed."))
