import tempfile
import unittest
from pathlib import Path

from check_submission_package import (
    check_forbidden_tracked,
    check_gitignore,
    check_large_tracked,
    check_required_paths,
)


class SubmissionPackageCheckTests(unittest.TestCase):
    def test_forbidden_tracked_files_are_reported(self):
        errors = check_forbidden_tracked(
            [
                "README.md",
                "dataset/for_hackathon/new_data",
                "capture.db3",
                "docs/demo.mp4",
                ".env",
            ]
        )

        self.assertEqual(len(errors), 4)
        self.assertTrue(any("dataset/for_hackathon/new_data" in error for error in errors))
        self.assertTrue(any("capture.db3" in error for error in errors))
        self.assertTrue(any("docs/demo.mp4" in error for error in errors))
        self.assertTrue(any(".env" in error for error in errors))

    def test_large_tracked_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "big.bin"
            path.write_bytes(b"x" * 11)

            errors = check_large_tracked(root, ["big.bin"], max_bytes=10)

        self.assertEqual(len(errors), 1)
        self.assertIn("big.bin", errors[0])

    def test_required_paths_and_gitignore_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in [
                "README.md",
                "SOLUTION.md",
                "Dockerfile",
                "models/noise_classifier_candidate_baseline_v2.json",
                "scripts/build_current_model_validation_dataset.py",
                "scripts/evaluate_current_model_real_synthetic.py",
                "scripts/prepare_hackathon_datasets.py",
                "scripts/run_stage_2_cpu_player.ps1",
                "scripts/run_submission_ros2_demo.ps1",
                "scripts/check_submission_package.py",
                "docs/README_REVIEWER_PLAYER_QUICKSTART.md",
                "docs/README_SUBMISSION_CHECKLIST.md",
                "docs/reports/submission/submission_gap_closure_20260927.md",
                "docs/reports/submission/headless_ros2_smoke_20260927.md",
                "src/lidar_mosmetro3d_cpp/package.xml",
                "src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp",
            ]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            (root / ".gitignore").write_text(
                "\n".join(["/dataset/", "/artefacts/", "*.db3", "*.tar", "*.zst", "*.mp4", "*.pptx", ".env"]),
                encoding="utf-8",
            )

            self.assertEqual(check_required_paths(root), [])
            self.assertEqual(check_gitignore(root), [])


if __name__ == "__main__":
    unittest.main()
