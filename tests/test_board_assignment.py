import unittest
from src.hardware.pressure.connection import BoardAssignmentWizard, AssignmentPhase

class TestBoardAssignmentWizard(unittest.TestCase):
    def setUp(self):
        self.wizard = BoardAssignmentWizard(board_a="BOARD_A_ID", board_b="BOARD_B_ID", threshold=5.0)

    def test_initial_state(self):
        self.assertEqual(self.wizard.phase, AssignmentPhase.IDLE)
        self.assertIsNone(self.wizard.left_board)
        self.assertIsNone(self.wizard.right_board)

    def test_start_wizard(self):
        self.wizard.start()
        self.assertEqual(self.wizard.phase, AssignmentPhase.WAITING_LEFT)
        self.assertIn("LEFT", self.wizard.message)

    def test_assignment_board_a_left_then_board_b_right(self):
        self.wizard.start()
        # No weight yet
        phase, msg = self.wizard.update(0.0, 0.0)
        self.assertEqual(phase, AssignmentPhase.WAITING_LEFT)

        # Step on both at once (ambiguous) -> should stay in WAITING_LEFT
        phase, msg = self.wizard.update(12.0, 10.0)
        self.assertEqual(phase, AssignmentPhase.WAITING_LEFT)

        # Step only on Board A
        phase, msg = self.wizard.update(15.0, 0.5)
        self.assertEqual(phase, AssignmentPhase.WAITING_RIGHT)
        self.assertEqual(self.wizard.left_board, "BOARD_A_ID")
        self.assertEqual(self.wizard.right_board, "BOARD_B_ID")
        self.assertIn("RIGHT", msg)

        # Step on Board B (while still or stepping onto Right)
        phase, msg = self.wizard.update(15.0, 20.0)
        self.assertEqual(phase, AssignmentPhase.COMPLETE)
        self.assertIn("Both", msg)
        self.assertTrue(self.wizard.get_status()["is_complete"])

    def test_assignment_board_b_left_then_board_a_right(self):
        self.wizard.start()
        # Step only on Board B
        phase, msg = self.wizard.update(0.2, 18.0)
        self.assertEqual(phase, AssignmentPhase.WAITING_RIGHT)
        self.assertEqual(self.wizard.left_board, "BOARD_B_ID")
        self.assertEqual(self.wizard.right_board, "BOARD_A_ID")

        # Step on Board A
        phase, msg = self.wizard.update(14.0, 18.0)
        self.assertEqual(phase, AssignmentPhase.COMPLETE)
        self.assertEqual(self.wizard.left_board, "BOARD_B_ID")
        self.assertEqual(self.wizard.right_board, "BOARD_A_ID")

    def test_reset(self):
        self.wizard.start()
        self.wizard.update(15.0, 0.0)
        self.wizard.reset()
        self.assertEqual(self.wizard.phase, AssignmentPhase.IDLE)
        self.assertIsNone(self.wizard.left_board)

if __name__ == "__main__":
    unittest.main()
