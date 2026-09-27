"""Static regression guards for the full C++ catalog workflow."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FullCppCatalogContractTest(unittest.TestCase):
    def test_exporter_requires_matching_cpp_identity_and_hash(self):
        source = (ROOT / "scripts" / "export_full_cpp_catalog.py").read_text(encoding="utf-8")
        self.assertIn("C++ header identity mismatch", source)
        self.assertIn("C++ source frame mismatch", source)
        self.assertIn("raw_xyzf", source)
        self.assertIn("development_candidate", source)
        self.assertIn('"cpp_result": result', source)
        self.assertIn("matching_cpp_runtime_attempts", source)
        self.assertIn("for runtime_attempts in range(1, 4)", source)

    def test_renderer_rechecks_raw_hash_and_never_computes_membership(self):
        source = (ROOT / "scripts" / "render_full_cpp_catalog_previews.py").read_text(encoding="utf-8")
        self.assertIn("raw XYZ SHA-256 mismatch", source)
        self.assertIn("core_source_indices", source)
        self.assertIn("margin_source_indices", source)
        self.assertNotIn("AnalyzeCurveEnvelope", source)
        self.assertNotIn("DetectAutoRails", source)

    def test_merger_rejects_overlap_or_incomplete_source_parts(self):
        source = (ROOT / "scripts" / "merge_full_cpp_catalog_shards.py").read_text(encoding="utf-8")
        self.assertIn("duplicated source part across shards", source)
        self.assertIn("not contiguous", source)
        self.assertIn("complete expected new_data interval", source)

    def test_concat_keeps_one_chapter_per_source_part(self):
        source = (ROOT / "scripts" / "concat_full_cpp_catalog_previews.py").read_text(encoding="utf-8")
        self.assertIn("len(chapters) != 221", source)
        self.assertIn("[CHAPTER]", source)
        self.assertIn(".chapters.json", source)

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
