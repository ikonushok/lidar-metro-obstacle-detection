import unittest
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config' / 'geometry_contract.yaml'


class GeometryContractTest(unittest.TestCase):
    def setUp(self):
        self.config = CONFIG_PATH.read_text(encoding='utf-8')

    def test_hackathon_profile_is_explicit_and_limited_to_livox(self):
        self.assertIn('status: ASSUMED_HACKATHON', self.config)
        self.assertIn('target_from_source: hackathon_track_lidar_livox <- lidar_livox', self.config)
        self.assertIn('lidar_livox: ASSUMED_HACKATHON_ACTIVE', self.config)
        self.assertIn('hesai_lidar: UNKNOWN_REQUIRES_SEPARATE_DEMO_PROFILE', self.config)

    def test_demo_contract_cannot_publish_clear_or_safety_decision(self):
        self.assertIn('obstacle_candidate_enabled: true', self.config)
        self.assertIn('geometric_decision_enabled: false', self.config)
        self.assertIn('safety_decision_permitted: false', self.config)
        self.assertIn('clear_decision_permitted: false', self.config)
        self.assertIn('candidate_result: OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY', self.config)
        self.assertIn('no_candidate_result: UNKNOWN', self.config)

    def test_production_replacement_evidence_remains_required(self):
        self.assertIn('production_revalidation_required: true', self.config)
        self.assertIn('- target_from_lidar_calibration', self.config)
        self.assertIn('margin: 0.20', self.config)
        self.assertIn('units: m', self.config)
        self.assertIn('units_status: ASSUMED_HACKATHON', self.config)
        self.assertIn('margin_unit: m', self.config)
        self.assertIn('margin_unit_status: ASSUMED_HACKATHON', self.config)

    def test_warning_layer_is_assumed_and_cannot_make_a_safety_decision(self):
        self.assertIn('warning_layer:', self.config)
        self.assertIn('left: 0.50', self.config)
        self.assertIn('right: 0.50', self.config)
        self.assertIn('top: 0.50', self.config)
        self.assertIn('bottom: 1.30', self.config)
        self.assertIn('safety_decision_permitted: false', self.config)


if __name__ == '__main__':
    unittest.main()
