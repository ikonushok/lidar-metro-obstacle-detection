import importlib.util
import types
from pathlib import Path
import sys
import unittest


archive_stub = types.ModuleType("archive_bag_frames")
archive_stub.ArchiveBagFrames = object
sys.modules["archive_bag_frames"] = archive_stub
SPEC = importlib.util.spec_from_file_location(
    "evaluate_noise_classifier",
    Path("scripts/evaluate_noise_classifier.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(Path("scripts").resolve()))
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
CANDIDATES_SPEC = importlib.util.spec_from_file_location(
    "evaluate_noise_model_candidates",
    Path("scripts/evaluate_noise_model_candidates.py"),
)
CANDIDATES_MODULE = importlib.util.module_from_spec(CANDIDATES_SPEC)
sys.modules[CANDIDATES_SPEC.name] = CANDIDATES_MODULE
CANDIDATES_SPEC.loader.exec_module(CANDIDATES_MODULE)


class EvaluateNoiseClassifierTemporalTest(unittest.TestCase):
    def test_model_temporal_suppresses_isolated_alarm(self):
        rows = [
            {"unknown": False, "model_alarm": False, "model_target_hit": False, "model_false_components": 0, "model_component_count": 0},
            {"unknown": False, "model_alarm": True, "model_target_hit": False, "model_false_components": 1, "model_component_count": 1},
            {"unknown": False, "model_alarm": False, "model_target_hit": False, "model_false_components": 0, "model_component_count": 0},
        ]

        MODULE.apply_model_temporal_confirmation(rows)

        self.assertFalse(rows[1]["model_temporal_alarm"])
        self.assertEqual(rows[1]["model_temporal_false_components"], 0)

    def test_model_temporal_confirms_second_consecutive_alarm(self):
        rows = [
            {"unknown": False, "model_alarm": True, "model_target_hit": True, "model_false_components": 0, "model_component_count": 1},
            {"unknown": False, "model_alarm": True, "model_target_hit": True, "model_false_components": 0, "model_component_count": 1},
            {"unknown": False, "model_alarm": False, "model_target_hit": False, "model_false_components": 0, "model_component_count": 0},
        ]

        MODULE.apply_model_temporal_confirmation(rows)

        self.assertFalse(rows[0]["model_temporal_alarm"])
        self.assertFalse(rows[0]["model_temporal_target_hit"])
        self.assertTrue(rows[1]["model_temporal_alarm"])
        self.assertTrue(rows[1]["model_temporal_target_hit"])

    def test_candidate_temporal_resets_on_unknown(self):
        rows = [
            {"source_id": "new_data", "unknown": False, "raw_alarm": True},
            {"source_id": "new_data", "unknown": True, "raw_alarm": False},
            {"source_id": "new_data", "unknown": False, "raw_alarm": True},
            {"source_id": "new_data", "unknown": False, "raw_alarm": True},
        ]

        CANDIDATES_MODULE.apply_temporal(rows, "raw_alarm", "temporal_alarm")

        self.assertFalse(rows[0]["temporal_alarm"])
        self.assertFalse(rows[2]["temporal_alarm"])
        self.assertTrue(rows[3]["temporal_alarm"])

    def test_candidate_temporal_legacy_adjacent_confirms_both_neighbors(self):
        rows = [
            {"source_id": "new_data", "unknown": False, "raw_alarm": True},
            {"source_id": "new_data", "unknown": False, "raw_alarm": True},
            {"source_id": "new_data", "unknown": False, "raw_alarm": False},
        ]

        CANDIDATES_MODULE.apply_temporal(
            rows, "raw_alarm", "temporal_alarm", temporal_mode="legacy_adjacent"
        )

        self.assertTrue(rows[0]["temporal_alarm"])
        self.assertTrue(rows[1]["temporal_alarm"])
        self.assertFalse(rows[2]["temporal_alarm"])

    def test_current_evaluator_preserves_unknown_reason(self):
        row = MODULE.analyze_frame(
            b"",
            {
                "status": "UNKNOWN",
                "reason": "AMBIGUOUS_LOCAL_CONTINUITY_PATH",
                "curve_axis_status": "MISSING_CURVE_AXIS",
                "rail_axis_failure_diagnostics": {
                    "best_path_score": 9,
                    "competing_path_score": 8,
                },
            },
            {},
            10,
            False,
        )

        self.assertTrue(row["unknown"])
        self.assertEqual(row["unknown_reason"], "AMBIGUOUS_LOCAL_CONTINUITY_PATH")
        self.assertEqual(row["curve_axis_status"], "MISSING_CURVE_AXIS")
        self.assertEqual(row["rail_axis_failure_diagnostics"]["best_path_score"], 9)

    def test_candidate_summary_reports_unknown_fp_reasons(self):
        rows = [
            {
                "source_id": "new_data",
                "frame": 94,
                "unknown": True,
                "target": False,
                "unknown_reason": "AMBIGUOUS_LOCAL_CONTINUITY_PATH",
                "curve_axis_status": "MISSING_CURVE_AXIS",
                "raw_alarm": False,
                "temporal_alarm": False,
                "target_hit": False,
                "temporal_target_hit": False,
                "temporal_false_components": 0,
            },
            {
                "source_id": "doubleT_obstacle",
                "frame": 13,
                "unknown": False,
                "target": True,
                "raw_alarm": True,
                "temporal_alarm": True,
                "target_hit": True,
                "temporal_target_hit": True,
                "temporal_false_components": 0,
            },
        ]

        summary = CANDIDATES_MODULE.summarize_rows(rows, 1.0)

        self.assertEqual(summary["unknown"], 1)
        self.assertEqual(
            summary["unknown_fp_reason_counts"],
            {"AMBIGUOUS_LOCAL_CONTINUITY_PATH": 1},
        )
        self.assertEqual(
            summary["unknown_reason_descriptions_ru"]["AMBIGUOUS_LOCAL_CONTINUITY_PATH"],
            "неоднозначная непрерывная цепочка рельсовой оси",
        )
        self.assertEqual(
            summary["unknown_fp_frame_keys_by_reason"],
            {"AMBIGUOUS_LOCAL_CONTINUITY_PATH": ["new_data:94"]},
        )

    def test_hard_negative_duration_limits_mining_window(self):
        frames = [
            {
                "source_id": "doubleT_obstacle",
                "frame": 13,
                "bag_offset_seconds": 0.0,
                "unknown": False,
                "components": [
                    {"component_id": 0, "features": [1.0] * 9, "label": True},
                ],
            },
            {
                "source_id": "new_data",
                "frame": 1,
                "bag_offset_seconds": 10.0,
                "unknown": False,
                "legacy_tree_v1_temporal_alarm": True,
                "components": [
                    {
                        "component_id": 0,
                        "features": [2.0] * 9,
                        "label": False,
                        "legacy_tree_v1_score": 0.9,
                    },
                ],
            },
            {
                "source_id": "new_data",
                "frame": 7000,
                "bag_offset_seconds": 700.0,
                "unknown": False,
                "legacy_tree_v1_temporal_alarm": True,
                "components": [
                    {
                        "component_id": 0,
                        "features": [3.0] * 9,
                        "label": False,
                        "legacy_tree_v1_score": 0.9,
                    },
                ],
            },
        ]

        rows, summary = CANDIDATES_MODULE.hard_negative_training_rows(
            frames,
            {"doubleT_obstacle"},
            {"new_data"},
            regular_negative_ratio=0,
            seed=7,
            hard_negative_max_duration_seconds=600.0,
        )

        self.assertEqual(summary["hard_negative_key_count"], 1)
        self.assertEqual(
            [row["frame"] for row in rows if row["training_role"] == "hard_negative"],
            [1],
        )


if __name__ == "__main__":
    unittest.main()
