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

    def test_assign_wizard_refuses_without_two_boards(self):
        """The wizard must not 'complete' when the hardware isn't there.

        It used to invent a "Board B" placeholder and drive itself from a
        single board's left/right cells, so a user with one board (or none)
        could walk it all the way to "both boards assigned" and end up with a
        dual configuration that never existed.
        """
        obs_server.pressure_manager.set_simulator(False)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/api/pressure/assign",
                data=json.dumps({"action": "start"}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            res = urllib.request.urlopen(req)
            self.assertEqual(res.getcode(), 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("phase"), "idle")
            self.assertFalse(data.get("is_complete"))
            self.assertIn("2 boards detected", data.get("message", ""))

            # Feeding it weight must not advance it either.
            req = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/api/pressure/assign",
                data=json.dumps({"action": "update", "weight_a": 35.0,
                                 "weight_b": 0.0}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            data = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
            self.assertNotEqual(data.get("phase"), "complete")
            self.assertFalse(data.get("is_complete"))
        finally:
            obs_server.pressure_manager.set_simulator(False)

    def test_assign_wizard_flow_in_simulator(self):
        """The step-order wizard still works where synthetic loads are valid."""
        obs_server.pressure_manager.set_simulator(True)
        try:
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
        finally:
            obs_server.pressure_manager.set_simulator(False)
            obs_server.pressure_manager.reset_assignment_wizard()

    def test_explicit_assign_rejects_bad_input(self):
        """assign_boards must refuse placeholders and same-board pairs."""
        pm = obs_server.pressure_manager
        self.assertEqual(pm.assign_boards("Board A", "Board B").get("status"), "error")
        self.assertEqual(pm.assign_boards(None, None).get("status"), "error")
        self.assertEqual(
            pm.assign_boards("/dev/input/event9", "/dev/input/event9").get("status"),
            "error",
        )

    def test_status_reports_real_device_count(self):
        res = urllib.request.urlopen(
            f"http://127.0.0.1:{TEST_PORT}/api/pressure/status")
        data = json.loads(res.read().decode("utf-8"))
        self.assertIn("device_count", data)
        self.assertIn("devices", data)
        self.assertEqual(data["device_count"], len(data["devices"]))
        # dual_ready must never be true without a real DualWbbBackend.
        if data.get("dual_ready"):
            self.assertTrue(data.get("assigned_left"))
            self.assertTrue(data.get("assigned_right"))

    def test_calibration_roundtrips_assignment(self):
        """assigned_left/right must survive a save -> load cycle.

        _save_calibration always wrote these keys but _load_calibration never
        read them back, so a dual setup silently reverted to unassigned on
        every launch.
        """
        import os as _os
        import tempfile
        pm = obs_server.pressure_manager
        fd, tmp = tempfile.mkstemp(suffix=".json")
        _os.close(fd)
        prev = (pm.assigned_left, pm.assigned_right, pm.board_mode)
        try:
            pm.assigned_left = "/dev/input/event20"
            pm.assigned_right = "/dev/input/event21"
            pm.board_mode = "dual"
            pm._save_calibration(tmp)

            pm.assigned_left = None
            pm.assigned_right = None
            pm.board_mode = "single"
            pm._load_calibration(tmp)

            self.assertEqual(pm.assigned_left, "/dev/input/event20")
            self.assertEqual(pm.assigned_right, "/dev/input/event21")
            self.assertEqual(pm.board_mode, "dual")
        finally:
            pm.assigned_left, pm.assigned_right, pm.board_mode = prev
            _os.unlink(tmp)

    def test_dual_mode_without_assignment_loads_as_single(self):
        """A dual label with no usable assignment is just single mode lying."""
        import json as _json
        import os as _os
        import tempfile
        pm = obs_server.pressure_manager
        fd, tmp = tempfile.mkstemp(suffix=".json")
        _os.close(fd)
        prev = (pm.assigned_left, pm.assigned_right, pm.board_mode)
        try:
            with open(tmp, "w") as f:
                _json.dump({"board_mode": "dual", "assigned_left": None,
                            "assigned_right": None}, f)
            pm.assigned_left = None
            pm.assigned_right = None
            pm._load_calibration(tmp)
            self.assertEqual(pm.board_mode, "single")
        finally:
            pm.assigned_left, pm.assigned_right, pm.board_mode = prev
            _os.unlink(tmp)

if __name__ == "__main__":
    unittest.main()
