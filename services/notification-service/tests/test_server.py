import importlib.util
import pathlib
import unittest

FILE = pathlib.Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("notification_server", FILE)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class NotificationTests(unittest.TestCase):
    def test_health(self):
        status, body = server.response("/health")
        self.assertEqual((status, body), (200, {"service": "notification-service", "status": "ok"}))

    def test_missing(self):
        self.assertEqual(server.response("/unknown")[0], 404)

    def test_version(self):
        self.assertEqual(server.response("/version")[0], 200)
