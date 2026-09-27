import unittest
from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config' / 'geometry_contract.yaml'


class GeometryContractTest(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load(CONFIG_PATH.read_text(encoding='utf-8'))

    def test_hackathon_profile_is_explicit_and_limited_to_livox(self):
        frames = self.config['frames']
        self.assertEqual(self.config['contract']['status'], 'ASSUMED_HACKATHON')
        self.assertEqual(frames['target_from_source'],
                         'hackathon_track_lidar_livox <- lidar_livox')
        self.assertEqual(frames['source_frame_policy']['lidar_livox'],
                         'ASSUMED_HACKATHON_ACTIVE')
        self.assertEqual(frames['source_frame_policy']['hesai_lidar'],
                         'UNKNOWN_REQUIRES_SEPARATE_DEMO_PROFILE')

    def test_demo_contract_cannot_publish_clear_or_safety_decision(self):
        activation = self.config['activation']
        self.assertTrue(activation['obstacle_candidate_enabled'])
        self.assertFalse(activation['geometric_decision_enabled'])
        self.assertFalse(activation['safety_decision_permitted'])
        self.assertFalse(activation['clear_decision_permitted'])
        self.assertEqual(activation['candidate_result'],
                         'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY')
        self.assertEqual(activation['no_candidate_result'], 'UNKNOWN')

    def test_production_replacement_evidence_remains_required(self):
        contract = self.config['contract']
        self.assertTrue(contract['production_revalidation_required'])
        self.assertIn('target_from_lidar_calibration',
                      contract['replacement_evidence_required'])
        self.assertEqual(self.config['safety_envelope']['margin'], 0.20)
        self.assertEqual(self.config['frames']['units'], 'm')
        self.assertEqual(self.config['frames']['units_status'], 'ASSUMED_HACKATHON')
        self.assertEqual(self.config['safety_envelope']['margin_unit'], 'm')
        self.assertEqual(self.config['safety_envelope']['margin_unit_status'], 'ASSUMED_HACKATHON')

    def test_warning_layer_is_assumed_and_cannot_make_a_safety_decision(self):
        warning = self.config['warning_layer']
        self.assertEqual(warning['status'], 'ASSUMED_HACKATHON')
        self.assertEqual(warning['offsets_from_profile_m'],
                         {'left': 0.5, 'right': 0.5, 'top': 0.5, 'bottom': 1.3})
        self.assertFalse(warning['safety_decision_permitted'])


if __name__ == '__main__':
    unittest.main()
