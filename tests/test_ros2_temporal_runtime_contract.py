import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp"
CHECKER = ROOT / "scripts/check_ros_model_pipeline.py"


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

        apply_pos = source.index("const auto temporal_decision = ApplyTemporalConfirmation")
        public_pos = source.index('<< "\\"intrusion_candidate_present\\":"')
        self.assertLess(apply_pos, public_pos)
        self.assertIn(
            "temporal_decision.confirmed_intrusion_candidate_present",
            source[apply_pos:public_pos],
        )

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


if __name__ == "__main__":
    unittest.main()
