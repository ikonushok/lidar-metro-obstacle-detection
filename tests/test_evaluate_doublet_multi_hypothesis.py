"""Focused contracts for doubleT multi-hypothesis summarization."""
import importlib.util
from pathlib import Path
import sys
import unittest


SPEC = importlib.util.spec_from_file_location(
    "evaluate_doublet_multi_hypothesis",
    Path("scripts/evaluate_doublet_multi_hypothesis.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(Path("scripts").resolve()))
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EvaluateDoubleTMultiHypothesisTest(unittest.TestCase):
    def test_union_gate_counts_positive_and_negative_frames(self):
        rows = [
            {"frame": 12, "target": False, "tangent_alarm": False, "arc_clamped_alarm": False, "union_alarm": False},
            {"frame": 13, "target": True, "tangent_alarm": True, "arc_clamped_alarm": False, "union_alarm": True},
            {"frame": 14, "target": True, "tangent_alarm": False, "arc_clamped_alarm": True, "union_alarm": True},
            {"frame": 15, "target": False, "tangent_alarm": False, "arc_clamped_alarm": False, "union_alarm": False},
        ]
        summary = MODULE.summarize(rows, 13, 14)
        self.assertTrue(summary["pass_doublet_obstacle_gate"])
        self.assertEqual(summary["union"]["tp_frames"], 2)
        self.assertEqual(summary["union"]["fp_frames"], 0)

    def test_union_gate_fails_on_false_positive(self):
        rows = [
            {"frame": 13, "target": True, "tangent_alarm": True, "arc_clamped_alarm": False, "union_alarm": True},
            {"frame": 12, "target": False, "tangent_alarm": False, "arc_clamped_alarm": True, "union_alarm": True},
        ]
        summary = MODULE.summarize(rows, 13, 13)
        self.assertFalse(summary["pass_doublet_obstacle_gate"])
        self.assertEqual(summary["union"]["fp_frame_indices"], [12])

    def test_unlabelled_source_reports_added_alarms_without_gate(self):
        rows = [
            {"frame": 227, "target": False, "tangent_alarm": False, "arc_clamped_alarm": True, "union_alarm": True},
            {"frame": 228, "target": False, "tangent_alarm": True, "arc_clamped_alarm": True, "union_alarm": True},
        ]
        summary = MODULE.summarize(rows, None, None)
        self.assertIsNone(summary["positive_interval_inclusive"])
        self.assertIsNone(summary["pass_doublet_obstacle_gate"])
        self.assertEqual(summary["union_added_alarm_frame_indices"], [227])


if __name__ == "__main__":
    unittest.main()
