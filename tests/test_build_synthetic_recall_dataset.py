import importlib.util
from pathlib import Path
import sys
import types
import unittest


archive_stub = types.ModuleType("archive_bag_frames")
archive_stub.ArchiveBagFrames = object
sys.modules["archive_bag_frames"] = archive_stub
sys.path.insert(0, str(Path("scripts").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
SPEC = importlib.util.spec_from_file_location(
    "build_synthetic_recall_dataset",
    Path("scripts/build_synthetic_recall_dataset.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BuildSyntheticRecallDatasetTest(unittest.TestCase):
    def test_stage5_split_policies_are_explicit(self):
        self.assertEqual(
            MODULE.split_for("standing_person", 100.0, "center", "roundT_doubleT", 7, "all_train"),
            "train",
        )
        self.assertEqual(
            MODULE.split_for("standing_person", 100.0, "center", "roundT_doubleT", 7,
                             "all_synthetic_held_out"),
            "synthetic_held_out",
        )
        self.assertIn("every generated placement -> train", MODULE.split_policy_rules("all_train"))

    def test_legacy_policy_is_unchanged_for_old_matrix(self):
        self.assertEqual(
            MODULE.split_for("standing_person", 60.0, "center", "roundT_doubleT", 7, "legacy_v1"),
            "synthetic_held_out",
        )
        self.assertEqual(
            MODULE.split_for("standing_person", 30.0, "left_boundary", "roundT_doubleT", 7, "legacy_v1"),
            "calibration",
        )


if __name__ == "__main__":
    unittest.main()
