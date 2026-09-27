import unittest

import numpy as np

from stage_2_driver_video import axis_roles, driver_projection, reference_gates
from stage_2_player import (PLAYER_FORMAT_VERSION, encode_xyz_frame, frame_record,
                            visual_reference_crop)


class DriverVideoTest(unittest.TestCase):
    def setUp(self):
        self.roles = axis_roles({'longitudinal_axis': 'y', 'lateral_axis': 'x', 'vertical_axis': 'z'})
        self.placement = {'forward_start_m': 0.0, 'forward_end_m': 40.0,
                          'track_centerline_lateral_m': 0.0, 'rail_head_vertical_m': 0.0}
        self.reference = {'lateral_min_m': -1.4, 'lateral_max_m': 1.4,
                          'vertical_min_m': 0.0, 'vertical_max_m': 3.7}

    def test_projection_filters_points_behind_or_too_far(self):
        xyz = np.array([[2.0, -10.0, 1.0], [0.0, 1.0, 0.0], [0.0, -50.0, 0.0]])
        projected, depth = driver_projection(xyz, self.roles, -1, 0.25, 40.0)
        np.testing.assert_allclose(projected, [[0.2, 0.1]])
        np.testing.assert_allclose(depth, [10.0])

    def test_gates_follow_reference_cross_section(self):
        gates = reference_gates(self.roles, self.placement, self.reference, depths_m=(10.0,))
        self.assertEqual(len(gates), 1)
        np.testing.assert_allclose(gates[0][0], [-0.14, 0.14, 0.14, -0.14, -0.14])
        np.testing.assert_allclose(gates[0][1], [0.0, 0.0, 0.37, 0.37, 0.0])

    def test_player_encoding_keeps_every_supplied_return_in_order(self):
        xyz = np.array([[1.0, 2.0, 3.0], [-4.0, 5.0, 6.0]], dtype=np.float64)
        encoded = encode_xyz_frame(xyz)
        self.assertEqual(len(encoded), 24)
        np.testing.assert_allclose(np.frombuffer(encoded, dtype='<f4').reshape(-1, 3), xyz)

    def test_player_record_marks_distance_as_visual_metadata(self):
        stats = {'header_ns': 5, 'frame': 'lidar_livox', 'points': 4, 'finite': 3,
                 'zero': 1, 'nonfinite': 0}
        record = frame_record(2, 1_500_000_000, stats, np.array([[3.0, 4.0, 0.0]]),
                              1_000_000_000, 'frames/frame_0002.xyzf')
        self.assertEqual(PLAYER_FORMAT_VERSION, 1)
        self.assertEqual(record['displayed_points'], 1)
        self.assertEqual(record['bag_offset_seconds'], 0.5)
        self.assertEqual(record['closest_return_distance_m'], 5.0)
        self.assertEqual(record['header_timestamp_ns'], '5')

    def test_visual_reference_crop_expands_only_the_visual_hypothesis(self):
        visual = {
            'source_axis_assumption': {'longitudinal_axis': 'y', 'longitudinal_sign': -1,
                                       'lateral_axis': 'x', 'vertical_axis': 'z', 'source_units': 'm'},
            'placement_in_source_coordinates': self.placement,
            'reference_cross_section': {
                'lateral_extent_m': {'min': -1.4, 'max': 1.4},
                'vertical_extent_above_rail_m': {'min': 0.0, 'max': 3.7},
            },
        }
        crop = visual_reference_crop(visual)
        self.assertFalse(crop['safety_decision_permitted'])
        self.assertEqual(crop['margins_m'], {
            'left': 0.5, 'right': 0.5, 'top': 0.5, 'bottom': 0.5,
        })
        self.assertEqual(crop['longitudinal_filter'], 'NONE')
        self.assertEqual(crop['bounds_source_coordinates'], {
            'x': {'min': -1.4, 'max': 1.4}, 'z': {'min': 0.0, 'max': 3.7},
        })


if __name__ == '__main__':
    unittest.main()
