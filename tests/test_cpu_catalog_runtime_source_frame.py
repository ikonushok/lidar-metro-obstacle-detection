"""Static regression contract for per-source C++ node startup."""
from pathlib import Path
import unittest


class CpuCatalogRuntimeSourceFrameTest(unittest.TestCase):
    def test_runtime_restarts_node_for_the_raw_frame_id(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_catalog_runtime.py').read_text(encoding='utf-8')
        self.assertIn("f'source_frame:={source_frame}'", source)
        self.assertIn("if self.source_frame != record['source_frame']:", source)
        self.assertIn('self._start_for_source_frame(record[\'source_frame\'])', source)
        self.assertNotIn("'source_frame:=hesai_lidar'", source)

    def test_runtime_passes_and_checks_explicit_rail_search_config(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_catalog_runtime.py').read_text(encoding='utf-8')
        self.assertIn('rail_forward_min_m=2.0', source)
        self.assertIn("f'rail_forward_min_m:={self.rail_search_config[\"forward_min_m\"]}'", source)
        self.assertIn("result.get('rail_search_config') != self.rail_search_config", source)

    def test_runtime_passes_and_checks_forward_extension_config(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_catalog_runtime.py').read_text(encoding='utf-8')
        self.assertIn("forward_extension_method='tangent'", source)
        self.assertIn("'arc_clamped'", source)
        self.assertIn("f'forward_extension_method:={self.forward_extension_config[\"method\"]}'", source)
        self.assertIn("f'min_arc_radius_m:={self.forward_extension_config[\"min_arc_radius_m\"]}'", source)
        self.assertIn("f'max_arc_turn_deg:={self.forward_extension_config[\"max_arc_turn_deg\"]}'", source)
        self.assertIn("f'arc_fit_window_pairs:={self.forward_extension_config[\"arc_fit_window_pairs\"]}'", source)
        self.assertIn("result.get('forward_extension_method') != self.forward_extension_config['method']", source)
        self.assertIn("result.get('min_arc_radius_m') != self.forward_extension_config['min_arc_radius_m']", source)
        self.assertIn("result.get('max_arc_turn_deg') != self.forward_extension_config['max_arc_turn_deg']", source)
        self.assertIn("result.get('arc_fit_window_pairs') != self.forward_extension_config['arc_fit_window_pairs']", source)

    def test_direct_unknown_cpp_result_keeps_requested_noise_filter_mode(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (root / 'scripts' / 'cpu_catalog_runtime.py').read_text(encoding='utf-8')
        cli = (root / 'src' / 'cpp' / 'curve_pipeline_stream_cli.cpp').read_text(encoding='utf-8')
        self.assertIn("result.get('noise_filter_mode', 'legacy') != self.noise_filter_mode", runtime)
        self.assertIn('bool use_model_filter', cli)
        self.assertIn('noise_filter_mode', cli)
        self.assertIn('use_model_filter ? "candidate_baseline_v2" : "legacy"', cli)
        self.assertIn('lean_benchmark, active_model_filter', cli)

    def test_direct_cpp_timing_uses_one_active_filter_by_default(self):
        root = Path(__file__).resolve().parents[1]
        cli = (root / 'src' / 'cpp' / 'curve_pipeline_stream_cli.cpp').read_text(encoding='utf-8')
        evaluator = (root / 'scripts' / 'evaluate_noise_classifier.py').read_text(encoding='utf-8')
        self.assertIn('--compare-noise-filters', cli)
        self.assertIn('"--compare-noise-filters"', evaluator)
        self.assertIn('if (!active_model_filter || compare_noise_filters)', cli)
        self.assertIn('if (active_model_filter || compare_noise_filters)', cli)
        self.assertNotIn('common_elapsed + legacy_filter_ms', cli)
        self.assertNotIn('common_elapsed + model_filter_ms', cli)
        self.assertIn('common_processing_ms + legacy_filter_ms + wireframe_ms', cli)
        self.assertIn('common_processing_ms + model_filter_ms + wireframe_ms', cli)

    def test_model_update_plan_keeps_direct_path_and_same_data_speed_comparison(self):
        root = Path(__file__).resolve().parents[1]
        doc = (root / 'docs' / 'README_noise_classifier.md').read_text(encoding='utf-8')
        self.assertIn('runtime_transport=direct_cpp', doc)
        self.assertIn('ROS2-узел остаётся отдельным адаптером', doc)
        self.assertIn('После обучения сравнить текущую и новую модель на одинаковых кадрах', doc)
        self.assertIn('способе вызова', doc)
        self.assertIn('не утверждать, что новая модель не замедляет плеер', doc)

    def test_runtime_waits_for_bidirectional_discovery_before_large_cloud_publish(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_catalog_runtime.py').read_text(encoding='utf-8')
        self.assertIn('self.publisher.get_subscription_count() > 0', source)
        self.assertIn('self.node.count_publishers(candidate_topic) > 0', source)

    def test_runtime_stops_the_complete_ros2_process_group_on_source_change(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_catalog_runtime.py').read_text(encoding='utf-8')
        self.assertIn('start_new_session=True', source)
        self.assertIn('os.killpg(self.process.pid, signal.SIGTERM)', source)


if __name__ == '__main__':
    unittest.main()
