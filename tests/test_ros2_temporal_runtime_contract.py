import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp"
STREAM_CLI = ROOT / "src/cpp/curve_pipeline_stream_cli.cpp"
CHECKER = ROOT / "scripts/check_ros_model_pipeline.py"
WRAPPER = ROOT / "scripts/run_submission_ros2_demo.ps1"


class Ros2TemporalRuntimeContractTest(unittest.TestCase):
    def test_ros2_node_publishes_temporal_confirmed_public_alarm(self):
        source = NODE.read_text(encoding="utf-8")

        self.assertIn('declare_parameter<bool>("temporal_confirmation_enabled", true)', source)
        self.assertIn(
            'declare_parameter<int>("temporal_required_consecutive_frames", 2)',
            source,
        )
        self.assertIn("header_timestamp_ns == temporal_last_stamp_ns_", source)
        self.assertIn("ResetTemporalState();", source)
        self.assertIn(
            'frame_intrusion_candidate_present ? "UNCONFIRMED_CORE_INTRUSION_CANDIDATE"',
            source,
        )
        self.assertIn("model_frame_intrusion_candidate_present", source)
        self.assertIn("model_temporal_confirmed_intrusion_candidate_present", source)
        self.assertIn("baseline_v3_early_temporal_confirmed_intrusion_candidate_present", source)
        self.assertIn("kBaselineV3EarlyRequiredConsecutiveFrames = 3", source)

        apply_pos = source.index("const auto temporal_decision = ApplyTemporalConfirmation")
        public_pos = source.index('<< "\\"intrusion_candidate_present\\":"')
        self.assertLess(apply_pos, public_pos)
        self.assertIn(
            "temporal_decision.confirmed_intrusion_candidate_present",
            source[apply_pos:public_pos],
        )

    def test_direct_stream_promotes_three_frame_early_candidate_to_public_alarm(self):
        source = STREAM_CLI.read_text(encoding="utf-8")

        self.assertIn("kBaselineV3EarlyRequiredConsecutiveFrames = 3", source)
        self.assertIn("baseline_v3_early_temporal_intrusion", source)
        self.assertIn("baseline_v3_early_temporal_confirmed_intrusion_candidate_present", source)
        self.assertIn("result.nearest_baseline_v3_early_candidate", source)
        self.assertIn("public_reportable_core_source_indices", source)

    def test_ros2_checker_no_longer_requires_direct_public_alarm_parity(self):
        tree = ast.parse(CHECKER.read_text(encoding="utf-8"))
        parity = next(
            node for node in tree.body
            if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == "PARITY_FIELDS"
                for target in node.targets)
        )
        fields = ast.literal_eval(parity.value)
        self.assertNotIn("intrusion_candidate_present", fields)
        self.assertNotIn("reportable_intrusion_candidate_present", fields)

    def test_ros2_checker_exercises_foreign_bag_failure_modes(self):
        source = CHECKER.read_text(encoding="utf-8")

        self.assertIn("UNSUPPORTED_POINTCLOUD_XYZ_SCHEMA", source)
        self.assertIn("UNSUPPORTED_SOURCE_FRAME", source)
        self.assertIn("original_pointcloud_point_step", source)
        self.assertIn("point_view(original)", source)
        self.assertIn("valid_indices", source)
        self.assertIn("source_switch", source)

    def test_submission_wrapper_accepts_customer_bag_topic_and_frame(self):
        source = WRAPPER.read_text(encoding="utf-8")

        self.assertIn("[string]$BagPath = ''", source)
        self.assertIn("[string]$InputTopic = '/sensing/lidar/hesai128/pointcloud'", source)
        self.assertIn("[string]$SourceFrame = 'lidar_livox'", source)
        self.assertIn("metadata.yaml", source)
        self.assertIn("-RecordingPath must point to an extracted ROS2 recording folder", source)
        self.assertIn("-p input_topic:=$InputTopic", source)
        self.assertIn("-p source_frame:=$SourceFrame", source)
        self.assertIn("-p output_topic:=$OutputTopic", source)
        self.assertIn("ros2 bag info /data", source)
        self.assertIn("ros2 bag play /data --rate $Rate --read-ahead-queue-size $ReadAheadQueueSize", source)


if __name__ == "__main__":
    unittest.main()
