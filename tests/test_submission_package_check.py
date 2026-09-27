import tempfile
import unittest
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_submission_package",
    ROOT / "scripts" / "check_submission_package.py",
)
check_submission_package = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_submission_package)

check_forbidden_tracked = check_submission_package.check_forbidden_tracked
check_gitignore = check_submission_package.check_gitignore
check_large_tracked = check_submission_package.check_large_tracked
check_required_paths = check_submission_package.check_required_paths


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
                "models/baseline_v3_runtime_policy.json",
                "scripts/archive_bag_frames.py",
                "scripts/check_ros_model_pipeline.py",
                "scripts/prepare_hackathon_datasets.py",
                "scripts/run_stage_2_cpu_player.ps1",
                "scripts/run_submission_ros2_demo.ps1",
                "scripts/serve_stage_2_cpu_catalog.py",
                "scripts/cpu_catalog_runtime.py",
                "scripts/validate_ros_model_pipeline.ps1",
                "scripts/check_submission_package.py",
                "docs/REVIEWER_QUICKSTART.md",
                "docs/SUBMISSION_CHECKLIST.md",
                "docs/METHODOLOGY.md",
                "docs/DEVELOPMENT_HISTORY_AND_STATUS.md",
                "docs/DATASETS_AND_ASSUMPTIONS.md",
                "docs/TRAIN_ENVELOPE_AND_LIMITATIONS.md",
                "docs/LIDAR_SPEC.md",
                "docs/hackathon_documentations/instruction.md",
                "docs/reports/submission/SUBMISSION_READINESS_REPORT.md",
                "docs/reports/submission/ROS2_HEADLESS_DEMO_VERIFICATION.md",
                "src/lidar_mosmetro3d_cpp/package.xml",
                "src/lidar_mosmetro3d_cpp/CMakeLists.txt",
                "src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp",
                "src/cpp/auto_rails_core.cpp",
                "src/cpp/curve_envelope_core.cpp",
                "src/cpp/curve_pipeline_stream_cli.cpp",
            ]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            (root / ".gitignore").write_text(
                "\n".join([
                    "/dataset/",
                    "/artefacts/",
                    "*.db3",
                    "*.tar",
                    "*.zst",
                    "*.mp4",
                    "*.pptx",
                    ".env",
                    "/scripts/research/",
                ]),
                encoding="utf-8",
            )

            self.assertEqual(check_required_paths(root), [])
            self.assertEqual(check_gitignore(root), [])


if __name__ == "__main__":
    unittest.main()
