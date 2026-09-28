"""The organizer review catalog must stay separate from runtime detector input."""

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from serve_stage_2_cpu_catalog import (  # noqa: E402
    load_review_objects, load_review_source_statuses)


class FakeObjectReviewCatalogTest(unittest.TestCase):
    def test_user_visibility_windows_are_separate_from_legacy_events(self):
        objects = load_review_objects(ROOT)
        self.assertEqual([item["object_id"] for item in objects],
                         [f"obj{index:02d}" for index in range(1, 11)])
        self.assertEqual([item["object_id"] for item in objects if item["frames_inclusive"] is None],
                         ["obj05", "obj08", "obj09", "obj10"])
        self.assertEqual(objects[0]["frames_inclusive"], [135, 228])
        self.assertEqual(objects[1]["frames_inclusive"], [353, 368])
        self.assertEqual(objects[5]["frames_inclusive"], [567, 581])
        self.assertEqual(objects[6]["frames_inclusive"], [617, 633])
        self.assertEqual(objects[8]["review_status"], "ambiguous_excluded")

    def test_primary_metric_definition_remains_unchanged(self):
        labels = json.loads((ROOT / "config/evaluation_labels.json").read_text(encoding="utf-8"))
        source = next(item for item in labels["sources"]
                      if item["source_id"] == "cloud_with_fake_obj")
        self.assertEqual(len(source["positive_events"]), 6)
        self.assertEqual(len(source["negative_events"]), 1)
        self.assertEqual(len(source["excluded_from_scoring"]), 3)
        self.assertEqual(source["positive_events"][0]["frames_inclusive"], [204, 216])
        new_data = next(item for item in labels["sources"] if item["source_id"] == "new_data")
        self.assertEqual(new_data["label_status"], "user_reported_no_obstacles")
        self.assertEqual(load_review_source_statuses(ROOT)["new_data"],
                         "user_reported_no_obstacles")

if __name__ == "__main__":
    unittest.main()
