import struct
from pathlib import Path
from types import SimpleNamespace as S
import unittest

import yaml

from stage_3_baseline import evaluate_cloud, load_geometry_contract, points_in_assumed_envelope


ROOT = Path(__file__).resolve().parents[1]


def cloud(points, frame='lidar_livox'):
    fields = [S(name=name, offset=offset, datatype=7, count=1)
              for name, offset in (('x', 0), ('y', 4), ('z', 8))]
    data = bytearray(len(points) * 12)
    for index, xyz in enumerate(points):
        struct.pack_into('<fff', data, index * 12, *xyz)
    return S(height=1, width=len(points), point_step=12, row_step=len(data), data=data,
             fields=fields, is_bigendian=False,
             header=S(frame_id=frame, stamp=S(sec=10, nanosec=20)))


class Stage3BaselineTest(unittest.TestCase):
    def setUp(self):
        self.config = load_geometry_contract(ROOT / 'config' / 'geometry_contract.yaml')

    def test_cluster_in_assumed_envelope_is_marked_as_candidate(self):
        result = evaluate_cloud(cloud([(0.0, -5.0, 1.0)] * 5), self.config)
        self.assertEqual(result['status'], 'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY')
        self.assertFalse(result['safety_decision_permitted'])
        self.assertFalse(result['clear_decision_permitted'])
        self.assertEqual(result['approximate_distance_label'], 'APPROXIMATE_M_ASSUMED_GEOMETRY')
        self.assertEqual(result['clusters'][0]['points'], 5)
        self.assertEqual(result['clusters'][0]['bounds_source_coordinates'], {
            'x': {'min': 0.0, 'max': 0.0}, 'y': {'min': -5.0, 'max': -5.0},
            'z': {'min': 1.0, 'max': 1.0},
        })

    def test_outside_envelope_never_becomes_clear(self):
        result = evaluate_cloud(cloud([(3.0, -5.0, 1.0)] * 5), self.config)
        self.assertEqual((result['status'], result['reason']),
                         ('UNKNOWN', 'NO_CLUSTER_IN_ASSUMED_ENVELOPE'))
        self.assertIsNone(result['approximate_nearest_distance_m'])

    def test_low_obstacle_at_rail_level_remains_a_candidate(self):
        result = evaluate_cloud(cloud([(0.0, -5.0, 0.0)] * 5), self.config)
        self.assertEqual(result['status'], 'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY')
        self.assertEqual(result['clusters'][0]['points'], 5)

    def test_left_warning_layer_is_distinct_from_core_candidate(self):
        result = evaluate_cloud(cloud([(-1.8, -5.0, 1.0)] * 5), self.config)
        self.assertEqual(result['status'], 'WARNING_CANDIDATE_ASSUMED_GEOMETRY')
        self.assertEqual(result['reason'], 'CLUSTER_INTERSECTS_ASSUMED_WARNING_LAYER')
        self.assertEqual(result['clusters'][0]['zone'], 'WARNING_LAYER_ASSUMED_GEOMETRY')

    def test_bottom_warning_layer_is_inclusive(self):
        result = evaluate_cloud(cloud([(0.0, -5.0, -1.3)] * 5), self.config)
        self.assertEqual(result['status'], 'WARNING_CANDIDATE_ASSUMED_GEOMETRY')

    def test_unsupported_frame_is_unknown(self):
        result = evaluate_cloud(cloud([(0.0, -5.0, 1.0)] * 5, frame='hesai_lidar'), self.config)
        self.assertEqual((result['status'], result['reason']),
                         ('UNKNOWN', 'SOURCE_FRAME_NOT_ACTIVE_FOR_HACKATHON_DEMO'))

    def test_boundary_point_is_inclusive_after_margin(self):
        xyz, depth = points_in_assumed_envelope(
            __import__('numpy').array([[1.6, -10.0, 3.9]]), self.config)
        self.assertEqual(len(xyz), 1)
        self.assertEqual(float(depth[0]), 10.0)

    def test_invalid_candidate_activation_is_unknown(self):
        config = yaml.safe_load(yaml.safe_dump(self.config))
        config['activation']['obstacle_candidate_enabled'] = False
        result = evaluate_cloud(cloud([(0.0, -5.0, 1.0)] * 5), config)
        self.assertEqual((result['status'], result['reason']),
                         ('UNKNOWN', 'OBSTACLE_CANDIDATE_DISABLED'))

    def test_auto_grade_adds_candidate_without_removing_straight_fallback(self):
        config = yaml.safe_load(yaml.safe_dump(self.config))
        estimate = config['auto_grade_path']['estimation']
        estimate.update({
            'fit_forward_range_m': [0.0, 40.0], 'bin_size_m': 10.0,
            'min_points_per_bin': 5, 'min_valid_bins': 4,
            'max_fit_residual_m': 0.01,
        })
        support = [(0.0, -depth, -1.0 - 0.02 * depth)
                   for depth in (5.0, 15.0, 25.0, 35.0) for _ in range(5)]
        result = evaluate_cloud(cloud(support + [(0.0, -100.0, -2.5)] * 5), config)
        self.assertEqual(result['path_profile']['status'], 'ACTIVE_ASSUMED_AUTO_GRADE')
        self.assertAlmostEqual(result['path_profile']['grade_m_per_m'], -0.02, places=5)
        self.assertTrue(any(cluster['path_hypothesis'] == 'AUTO_GRADE'
                            for cluster in result['clusters']))
        self.assertEqual(result['status'], 'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY')

    def test_missing_auto_grade_support_keeps_outside_point_unknown(self):
        result = evaluate_cloud(cloud([(0.0, -100.0, -2.5)] * 5), self.config)
        self.assertEqual(result['path_profile']['status'], 'UNKNOWN_INSUFFICIENT_SUPPORT')
        self.assertEqual((result['status'], result['reason']),
                         ('UNKNOWN', 'NO_CLUSTER_IN_ASSUMED_ENVELOPE'))

    def test_local_track_polyline_follows_turn_and_grade_reversal_without_losing_fallback(self):
        config = yaml.safe_load(yaml.safe_dump(self.config))
        config['auto_grade_path']['enabled'] = False
        estimate = config['auto_track_path']['estimation']
        estimate.update({
            'fit_forward_range_m': [0.0, 50.0], 'bin_size_m': 10.0,
            'min_points_per_bin': 5, 'min_valid_bins': 4,
            'floor_band_above_quantile_m': 0.01,
            'max_lateral_step_m': 2.0, 'max_abs_grade': 0.20,
        })
        support_nodes = ((5.0, 0.0, -1.0), (15.0, 0.4, -1.2),
                         (25.0, 0.9, -1.4), (35.0, 0.5, -1.2),
                         (45.0, 0.1, -1.0))
        support = [(x, -depth, z) for depth, x, z in support_nodes for _ in range(5)]
        turning_candidate = [(0.9, -25.0, -0.4)] * 5
        straight_only_candidate = [(0.0, -2.0, 1.0)] * 5
        result = evaluate_cloud(cloud(support + turning_candidate + straight_only_candidate), config)
        track = result['path_profiles']['auto_track']
        self.assertEqual(track['status'], 'ACTIVE_ASSUMED_AUTO_TRACK')
        self.assertEqual(len(track['nodes']), 5)
        self.assertGreater(track['nodes'][2]['x_m'], track['nodes'][0]['x_m'])
        self.assertLess(track['nodes'][2]['z_m'], track['nodes'][0]['z_m'])
        self.assertGreater(track['nodes'][4]['z_m'], track['nodes'][2]['z_m'])
        self.assertTrue(any('AUTO_TRACK' in item['path_hypothesis'] for item in result['clusters']))
        self.assertTrue(any('STRAIGHT_FALLBACK' in item['path_hypothesis'] for item in result['clusters']))
        self.assertEqual(result['status'], 'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY')


if __name__ == '__main__':
    unittest.main()
