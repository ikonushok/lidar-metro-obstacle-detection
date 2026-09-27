"""Static regression guards for the full C++ catalog workflow."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FullCppCatalogContractTest(unittest.TestCase):
    def test_unknown_axis_diagnostics_include_ambiguous_path_metrics(self):
        auto_header = (ROOT / "src" / "cpp" / "auto_rails_core.hpp").read_text(encoding="utf-8")
        auto_core = (ROOT / "src" / "cpp" / "auto_rails_core.cpp").read_text(encoding="utf-8")
        stream_cli = (ROOT / "src" / "cpp" / "curve_pipeline_stream_cli.cpp").read_text(encoding="utf-8")
        ros_node = (
            ROOT / "src" / "lidar_mosmetro3d_cpp" / "src" / "curve_envelope_node.cpp"
        ).read_text(encoding="utf-8")

        for field in (
            "best_path_score",
            "best_path_cost",
            "best_path_coverage",
            "competing_path_score",
            "competing_path_cost",
            "competing_path_lateral_displacement_m",
            "best_path_pairs",
            "competing_path_pairs",
        ):
            self.assertIn(field, auto_header)
        for field in (
            "best_path_score",
            "best_path_cost",
            "best_path_coverage",
            "competing_path_score",
            "competing_path_cost",
            "competing_path_lateral_displacement_m",
            "best_path_pairs_source_xyz",
            "competing_path_pairs_source_xyz",
        ):
            self.assertIn(field, stream_cli)
            self.assertIn(field, ros_node)
        self.assertIn("AMBIGUOUS_LOCAL_CONTINUITY_PATH", auto_core)
        self.assertIn("rail_axis_failure_diagnostics", stream_cli)
        self.assertIn("rail_axis_failure_diagnostics", ros_node)


if __name__ == "__main__":
    unittest.main()
