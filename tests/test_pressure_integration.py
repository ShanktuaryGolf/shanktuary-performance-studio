"""Integration test for OBS server pressure endpoints and WebSocket frames."""

import http.client
import json
import sys
import time
import unittest
import urllib.request

sys.path.insert(0, '/home/sean/sps')
import obs_server

TEST_PORT = 9333

class TestPressureIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_thread = obs_server.launch_obs_server_thread(port=TEST_PORT)
        # Wait up to 3s for server to start
        for _ in range(30):
            try:
                res = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/pressure/status", timeout=1)
                if res.getcode() == 200:
                    break
            except Exception:
                time.sleep(0.1)

    def test_status_endpoint(self):
        res = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/pressure/status")
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertTrue(data.get("connected"))
        self.assertIn("latest", data)
        self.assertIn("mode", data)

    def test_tare_endpoint(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/tare",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")

    def test_cross_origin_post_is_rejected(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/simulator",
            data=json.dumps({"enabled": True}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://attacker.example",
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(req)
        self.assertEqual(context.exception.code, 403)

    def test_same_origin_post_is_allowed(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/simulator",
            data=json.dumps({"enabled": True}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{TEST_PORT}",
            }
        )
        res = urllib.request.urlopen(req)
        self.assertEqual(res.getcode(), 200)

    def test_cross_site_fetch_post_is_rejected(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/simulator",
            data=json.dumps({"enabled": True}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Sec-Fetch-Site": "cross-site",
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(req)
        self.assertEqual(context.exception.code, 403)

    def test_cross_origin_websocket_is_rejected(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/ws",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "dGVzdA==",
                "Origin": "https://attacker.example",
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(req)
        self.assertEqual(context.exception.code, 403)

    def test_headerless_websocket_handshake_is_allowed(self):
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT)
        conn.request(
            "GET", "/ws",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "dGVzdA==",
            }
        )
        self.assertEqual(conn.getresponse().status, 101)
        conn.close()

    def test_same_origin_websocket_handshake_is_allowed(self):
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT)
        conn.request(
            "GET", "/ws",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "dGVzdA==",
                "Origin": f"http://127.0.0.1:{TEST_PORT}",
            }
        )
        self.assertEqual(conn.getresponse().status, 101)
        conn.close()

    def test_simulator_toggle_endpoint(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/simulator",
            data=json.dumps({"enabled": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("mode"), "simulator")

    def test_pin_endpoint(self):
        res = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/pressure/pin")
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("host_mac", data)
        self.assertIn("pin_display", data)
        self.assertIn("platform", data)

    def test_open_bt_settings_endpoint(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/open_bt_settings",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")

if __name__ == "__main__":
    unittest.main()
