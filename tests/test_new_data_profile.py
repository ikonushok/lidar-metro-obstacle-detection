from copy import deepcopy
from pathlib import Path
import unittest

from stage_3_baseline import evaluate_cloud, load_geometry_contract
from test_stage_3_baseline import cloud

ROOT = Path(__file__).resolve().parents[1]


class NewDataProfileTest(unittest.TestCase):
    def setUp(self):
        self.config = load_geometry_contract(ROOT / 'config/geometry_new_data_experiment.yaml')

    def test_low_return_uses_new_rail_height_and_preserves_source(self):
        msg = cloud([(0, -5, -1.1)] * 5, 'hesai_lidar')
        before = bytes(msg.data)
        result = evaluate_cloud(msg, self.config)
        self.assertEqual(result['status'], 'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY')
        self.assertEqual(result['source_frame'], 'hesai_lidar')
        self.assertEqual(before, bytes(msg.data))
        self.assertAlmostEqual(result['clusters'][0]['bounds_source_coordinates']['z']['min'], -1.1)
        self.assertFalse(result['safety_decision_permitted'])
        self.assertFalse(result['clear_decision_permitted'])

    def test_margin_boundary_and_no_clear_outside(self):
        at_boundary = evaluate_cloud(cloud([(1.6, -5, 2.8)] * 5, 'hesai_lidar'), self.config)
        self.assertEqual(at_boundary['clusters'][0]['zone'], 'CORE_ASSUMED_ENVELOPE')
        outside = evaluate_cloud(cloud([(4, -5, 0)] * 5, 'hesai_lidar'), self.config)
        self.assertEqual(outside['status'], 'UNKNOWN')

    def test_wrong_frame_and_old_profile_remain_unknown(self):
        self.assertEqual(evaluate_cloud(cloud([(0, -5, 0)] * 5), self.config)['status'], 'UNKNOWN')
        old = load_geometry_contract(ROOT / 'config/geometry_contract.yaml')
        result = evaluate_cloud(cloud([(0, -5, 0)] * 5, 'hesai_lidar'), old)
        self.assertEqual(result['reason'], 'SOURCE_FRAME_NOT_ACTIVE_FOR_HACKATHON_DEMO')

    def test_transform_must_be_actual_source_identity(self):
        variants = []
        for field, value in [('working_frame', 'base_link'),
                             ('target_from_source', 'hesai_lidar <- base_link')]:
            changed = deepcopy(self.config)
            changed['frames'][field] = value
            variants.append(changed)
        for name, value in [('translation_m', [0, 0, 1]), ('rotation_xyzw', [0, 0, 1, 0])]:
            changed = deepcopy(self.config)
            changed['frames']['lidar_mounting_extrinsics']['transform'][name] = value
            variants.append(changed)
        for changed in variants:
            with self.subTest(config=changed['frames']):
                result = evaluate_cloud(cloud([(0, -5, 0)] * 5, 'hesai_lidar'), changed)
                self.assertEqual(result['reason'], 'INVALID_SOURCE_FRAME_IDENTITY_EXPERIMENT')

    def test_unimplemented_axes_or_safety_activation_are_rejected(self):
        mutations = [(['frames', 'axis_directions', 'y'], 'POSITIVE_Y'),
                     (['path', 'rail_centerline_in_working_frame', 'forward_axis'], '+y'),
                     (['activation', 'clear_decision_permitted'], True),
                     (['activation', 'safety_decision_permitted'], True)]
        for keys, value in mutations:
            changed = deepcopy(self.config)
            node = changed
            for key in keys[:-1]:
                node = node[key]
            node[keys[-1]] = value
            with self.subTest(keys=keys):
                result = evaluate_cloud(cloud([(0, -5, 0)] * 5, 'hesai_lidar'), changed)
                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertEqual(result['clusters'], [])


if __name__ == '__main__':
    unittest.main()
