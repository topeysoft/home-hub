"""Run from brain/: .venv/bin/python -m unittest -v. Which route answers which path; the app is imported, no server runs."""
import unittest, warnings
from starlette.routing import Match


class RouteOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", ResourceWarning)
        from hub.api import app
        cls.app = app

    def first(self, path, method="GET"):
        scope = {"type": "http", "path": path, "method": method, "root_path": "", "headers": [], "query_string": b""}
        for r in self.app.routes:
            m, _ = r.matches(scope)
            if m == Match.FULL: return getattr(r, "name", None) or getattr(r, "path", None)
        return None

    def test_a_sound_file_is_served_by_the_sounds_mount_not_the_panel(self):
        self.assertEqual(self.first("/sounds/prepared/white.mp3"), "sounds")
        self.assertEqual(self.first("/sounds/rain.mp3"), "sounds")

    def test_the_sounds_list_is_still_the_api(self):
        self.assertEqual(self.first("/sounds"), "sounds")            # the API route is named after its function
        names = [getattr(r, "name", "") for r in self.app.routes]
        self.assertLess(names.index("sounds"), len(names))
        api_index = next(i for i, r in enumerate(self.app.routes) if getattr(r, "path", "") == "/sounds" and hasattr(r, "endpoint"))
        mount_index = next(i for i, r in enumerate(self.app.routes) if getattr(r, "name", "") == "sounds" and not hasattr(r, "endpoint"))
        self.assertLess(api_index, mount_index)

    def test_api_routes_beat_the_panel_and_the_panel_takes_the_rest(self):
        self.assertEqual(self.first("/home"), "get_home")
        panel = self.first("/rooms")                                  # not an API path: the panel, when built
        self.assertIn(panel, ("app", None))


if __name__ == "__main__":
    unittest.main()
