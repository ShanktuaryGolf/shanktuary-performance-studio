import json
import sys
import time
import unittest
import urllib.request

sys.path.insert(0, '/home/sean/sps')
import obs_server

TEST_PORT = 9334

class TestDualPressureIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_thread = obs_server.launch_obs_server_thread(port=TEST_PORT)
        for _ in range(30):
            try:
                res = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/pressure/status", timeout=1)
                if res.getcode() == 200:
                    break
            except Exception:
                time.sleep(0.1)

    def test_mode_get_and_post(self):
        # GET mode
        res = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/pressure/mode")
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertIn("board_mode", data)

        # POST mode switch to dual
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/mode",
            data=json.dumps({"mode": "dual"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("board_mode"), "dual")

        # Switch back to single
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/mode",
            data=json.dumps({"mode": "single"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("board_mode"), "single")

    def test_assign_wizard_flow(self):
        # Start wizard
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/assign",
            data=json.dumps({"action": "start"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        self.assertEqual(res.getcode(), 200)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("phase"), "waiting_left")

        # Update step on Board A
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/assign",
            data=json.dumps({"action": "update", "weight_a": 15.0, "weight_b": 0.0}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("phase"), "waiting_right")

        # Update step on Board B
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/assign",
            data=json.dumps({"action": "update", "weight_a": 15.0, "weight_b": 20.0}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data.get("phase"), "complete")
        self.assertTrue(data.get("is_complete"))

if __name__ == "__main__":
    unittest.main()
