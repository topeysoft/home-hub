"""Bringing a fresh engine up without anyone seeing it.

This is the out-of-the-box path: a person plugs the hub in, types their name, and everything HA
normally asks is answered here. It talks plain HTTP, so the engine is replaced by a stand-in that
records what was asked and answers the way HA does.

Run from brain/: .venv/bin/python -m unittest -v
"""
import io, json, unittest, urllib.error
from unittest import mock

from hub import ha_setup
from hub.ha_setup import SetupError

URL = "http://ha:8123"


class FakeEngine:
    """HA's HTTP side. `routes` maps a path to (status, body) or a callable taking the decoded body."""
    def __init__(self, routes):
        self.routes = routes
        self.asked = []          # (method, path, body)

    def __call__(self, request, timeout=None):
        path = request.full_url[len(URL):]
        raw = request.data.decode() if request.data else ""
        try: body = json.loads(raw) if raw.startswith("{") else raw
        except ValueError: body = raw
        self.asked.append((request.get_method(), path, body))
        route = self.routes.get(path, (404, ""))
        status, payload = route(body) if callable(route) else route
        text = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "", {}, io.BytesIO(text.encode()))
        return _Response(status, text)


class _Response:
    def __init__(self, status, text): self.status, self.text = status, text
    def read(self): return self.text.encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


def serving(routes):
    return mock.patch.object(ha_setup.urllib.request, "urlopen", FakeEngine(routes))


class DriverStateTests(unittest.TestCase):
    def test_an_engine_nobody_has_set_up_yet_is_fresh(self):
        with serving({"/api/onboarding": (200, [{"step": "user", "done": False}])}):
            self.assertEqual(ha_setup.driver_state(URL), "fresh")

    def test_an_engine_with_an_owner_is_done(self):
        with serving({"/api/onboarding": (200, [{"step": "user", "done": True}, {"step": "core_config", "done": False}])}):
            self.assertEqual(ha_setup.driver_state(URL), "done")

    def test_an_engine_that_finished_onboarding_takes_the_question_away_and_that_also_means_done(self):
        # HA removes the endpoint once onboarding is over, so a 404 here is good news, not a failure.
        with serving({"/api/onboarding": (404, "")}):
            self.assertEqual(ha_setup.driver_state(URL), "done")

    def test_an_engine_answering_nonsense_is_a_problem_worth_raising(self):
        with serving({"/api/onboarding": (200, {"not": "a list"})}):
            with self.assertRaises(SetupError):
                ha_setup.driver_state(URL)


class CreateOwnerTests(unittest.TestCase):
    def routes(self, users=None):
        return {"/api/onboarding/users": users or (200, {"auth_code": "AC"}),
                "/auth/token": (200, {"access_token": "AT", "refresh_token": "RT"}),
                "/api/onboarding/core_config": (200, {}), "/api/onboarding/analytics": (200, {}),
                "/api/onboarding/integration": (200, {})}

    def test_the_owner_is_made_with_a_password_nobody_has_to_think_of(self):
        engine = FakeEngine(self.routes())
        with mock.patch.object(ha_setup.urllib.request, "urlopen", engine):
            acct = ha_setup.create_owner(URL, "Temi Adeyeri")
        self.assertEqual(acct["username"], "temiadeyeri")
        self.assertGreaterEqual(len(acct["password"]), 20)       # generated, not guessable
        self.assertEqual(acct["access"], "AT")

    def test_the_rest_of_onboarding_is_answered_so_nobody_ever_sees_it(self):
        engine = FakeEngine(self.routes())
        with mock.patch.object(ha_setup.urllib.request, "urlopen", engine):
            ha_setup.create_owner(URL, "Temi")
        asked = [path for _, path, _ in engine.asked]
        for step in ("/api/onboarding/core_config", "/api/onboarding/analytics", "/api/onboarding/integration"):
            self.assertIn(step, asked)

    def test_two_hubs_set_up_the_same_day_do_not_get_the_same_password(self):
        with mock.patch.object(ha_setup.urllib.request, "urlopen", FakeEngine(self.routes())):
            first = ha_setup.create_owner(URL, "Temi")
            second = ha_setup.create_owner(URL, "Temi")
        self.assertNotEqual(first["password"], second["password"])

    def test_an_engine_that_refuses_the_owner_says_why_rather_than_failing_silently(self):
        with mock.patch.object(ha_setup.urllib.request, "urlopen", FakeEngine(self.routes(users=(400, {"message": "username taken"})))):
            with self.assertRaises(SetupError) as e:
                ha_setup.create_owner(URL, "Temi")
        self.assertIn("username taken", str(e.exception))

    def test_a_token_exchange_that_fails_is_not_mistaken_for_success(self):
        routes = self.routes() | {"/auth/token": (400, {"error": "invalid_grant"})}
        with mock.patch.object(ha_setup.urllib.request, "urlopen", FakeEngine(routes)):
            with self.assertRaises(SetupError) as e:
                ha_setup.create_owner(URL, "Temi")
        self.assertIn("token exchange failed", str(e.exception))


class LoginTests(unittest.TestCase):
    def routes(self, step=None):
        return {"/auth/login_flow": (200, {"flow_id": "F1"}),
                "/auth/login_flow/F1": step or (200, {"type": "create_entry", "result": "AC"}),
                "/auth/token": (200, {"access_token": "AT", "refresh_token": "RT"})}

    def test_signing_in_to_an_engine_someone_set_up_by_hand_gets_a_token(self):
        with mock.patch.object(ha_setup.urllib.request, "urlopen", FakeEngine(self.routes())):
            self.assertEqual(ha_setup.login(URL, "temi", "pw")["access"], "AT")

    def test_a_wrong_password_is_told_in_words_a_person_can_act_on(self):
        step = (200, {"type": "form", "errors": {"base": "invalid_auth"}})
        with mock.patch.object(ha_setup.urllib.request, "urlopen", FakeEngine(self.routes(step))):
            with self.assertRaises(SetupError) as e:
                ha_setup.login(URL, "temi", "wrong")
        self.assertIn("did not work", str(e.exception))

    def test_an_engine_with_no_sign_in_to_offer_says_it_is_unavailable_rather_than_wrong_password(self):
        with mock.patch.object(ha_setup.urllib.request, "urlopen", FakeEngine({"/auth/login_flow": (500, "boom")})):
            with self.assertRaises(SetupError) as e:
                ha_setup.login(URL, "temi", "pw")
        self.assertIn("unavailable", str(e.exception))

    def test_the_password_is_never_put_in_the_address(self):
        engine = FakeEngine(self.routes())
        with mock.patch.object(ha_setup.urllib.request, "urlopen", engine):
            ha_setup.login(URL, "temi", "hunter2")
        for _, path, _ in engine.asked:
            self.assertNotIn("hunter2", path)


class LongLivedTokenTests(unittest.IsolatedAsyncioTestCase):
    class FakeWS:
        def __init__(self, frames): self.frames, self.sent = list(frames), []
        async def recv(self): return json.dumps(self.frames.pop(0))
        async def send(self, raw): self.sent.append(json.loads(raw))
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    def connecting(self, frames):
        ws = self.FakeWS(frames)
        return ws, mock.patch.object(ha_setup.websockets, "connect", mock.Mock(return_value=ws))

    async def test_the_key_the_brain_will_use_from_then_on_is_minted_and_lasts_years(self):
        ws, patched = self.connecting([{"type": "auth_required"}, {"type": "auth_ok"}, {"id": 1, "success": True, "result": "LLT"}])
        with patched:
            self.assertEqual(await ha_setup.long_lived_token(URL, "AT"), "LLT")
        minted = next(m for m in ws.sent if m.get("type") == "auth/long_lived_access_token")
        self.assertGreaterEqual(minted["lifespan"], 3650)        # a hub nobody touches must not lock itself out

    async def test_an_engine_that_will_not_take_the_fresh_token_says_so(self):
        _, patched = self.connecting([{"type": "auth_required"}, {"type": "auth_invalid"}])
        with patched:
            with self.assertRaises(SetupError):
                await ha_setup.long_lived_token(URL, "AT")

    async def test_an_engine_that_refuses_to_mint_one_says_so(self):
        _, patched = self.connecting([{"type": "auth_required"}, {"type": "auth_ok"}, {"id": 1, "success": False, "error": {"message": "no"}}])
        with patched:
            with self.assertRaises(SetupError):
                await ha_setup.long_lived_token(URL, "AT")


if __name__ == "__main__":
    unittest.main()
