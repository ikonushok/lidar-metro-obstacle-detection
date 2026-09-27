import struct
from pathlib import Path
from types import SimpleNamespace as S
import unittest

import numpy as np

from cloud_input import point_view
from synthetic_obstacle_generator import (
    augment_pointcloud2,
    raycast_scene,
    scenario_catalog,
    select_scenario,
    validate_synthetic_config,
)


ROOT = Path(__file__).resolve().parents[1]


def base_config(obstacles=None):
    return {
        'status': 'SYNTHETIC_DEVELOPMENT_ONLY',
        'source_frame': 'lidar_livox',
        'target_from_source': 'lidar_livox <- lidar_livox',
        'units': 'm',
        'sensor_origin_xyz': [0.0, 0.0, 0.0],
        'minimum_range_m': 0.1,
        'occlusion_epsilon_m': 1e-6,
        'random_seed': 7,
        'dropout_probability': 0.0,
        'safety_decision_permitted': False,
        'clear_decision_permitted': False,
        'intensity': {'mode': 'constant', 'value': 42.0},
        'obstacles': obstacles or [{
            'id': 'box', 'shape': 'box', 'center_xyz': [0.0, -5.0, 0.0],
            'size_xyz': [2.0, 2.0, 2.0], 'yaw_deg': 0.0,
        }],
    }


def cloud(points, frame='lidar_livox', bigendian=False):
    fields = [S(name=name, offset=offset, datatype=datatype, count=1)
              for name, offset, datatype in (
                  ('x', 0, 7), ('y', 4, 7), ('z', 8, 7), ('intensity', 12, 7),
                  ('ring', 16, 4), ('timestamp', 18, 8))]
    point_step = 26
    width = len(points)
    row_step = width * point_step + 5
    data = bytearray(row_step)
    prefix = '>' if bigendian else '<'
    for index, xyz in enumerate(points):
        struct.pack_into(prefix + 'ffffHd', data, index * point_step,
                         *xyz, 3.5 + index, 100 + index, 123.25 + index)
    data[-5:] = b'PAD!!'
    return S(height=1, width=width, point_step=point_step, row_step=row_step,
             data=data, fields=fields, is_bigendian=bigendian,
             header=S(frame_id=frame, stamp=S(sec=10, nanosec=20)))


class SyntheticObstacleGeneratorTest(unittest.TestCase):
    def test_box_occludes_background_but_not_nearer_return(self):
        xyz = np.array([
            [0.0, -10.0, 0.0],
            [3.0, -10.0, 0.0],
            [0.0, -2.0, 0.0],
            [0.0, 0.0, 0.0],
        ])
        augmented, labels, truth = raycast_scene(xyz, base_config())
        np.testing.assert_allclose(augmented[0], [0.0, -4.0, 0.0])
        np.testing.assert_allclose(augmented[1:], xyz[1:])
        np.testing.assert_array_equal(labels, [0, -1, -1, -1])
        self.assertEqual(truth['synthetic_returns'], 1)
        self.assertAlmostEqual(truth['obstacles'][0]['nearest_return_m'], 4.0)

    def test_vertical_cylinder_includes_side_and_cap(self):
        config = base_config([{
            'id': 'person', 'shape': 'cylinder', 'center_xyz': [0.0, -5.0, 0.0],
            'radius_m': 1.0, 'height_m': 2.0,
        }])
        xyz = np.array([[0.0, -10.0, 0.0]])
        augmented, labels, _ = raycast_scene(xyz, config)
        np.testing.assert_allclose(augmented[0], [0.0, -4.0, 0.0])
        self.assertEqual(labels[0], 0)

        cap_config = base_config([{
            'id': 'cap', 'shape': 'cylinder', 'center_xyz': [0.0, -5.0, -5.0],
            'radius_m': 2.0, 'height_m': 2.0,
        }])
        cap_augmented, cap_labels, _ = raycast_scene(
            np.array([[0.0, -10.0, -10.0]]), cap_config)
        np.testing.assert_allclose(cap_augmented[0], [0.0, -4.0, -4.0])
        self.assertEqual(cap_labels[0], 0)

    def test_nearest_obstacle_wins(self):
        config = base_config([
            {'id': 'far', 'shape': 'box', 'center_xyz': [0.0, -7.0, 0.0],
             'size_xyz': [2.0, 2.0, 2.0]},
            {'id': 'near', 'shape': 'cylinder', 'center_xyz': [0.0, -3.0, 0.0],
             'radius_m': 0.5, 'height_m': 2.0},
        ])
        augmented, labels, truth = raycast_scene(np.array([[0.0, -10.0, 0.0]]), config)
        np.testing.assert_allclose(augmented[0], [0.0, -2.5, 0.0])
        self.assertEqual(labels[0], 1)
        self.assertEqual(truth['obstacles'][0]['synthetic_returns'], 0)
        self.assertEqual(truth['obstacles'][1]['synthetic_returns'], 1)

    def test_oriented_box_applies_yaw_in_source_frame(self):
        config = base_config([{
            'id': 'rotated', 'shape': 'box', 'center_xyz': [0.0, -5.0, 0.0],
            'size_xyz': [4.0, 1.0, 2.0], 'yaw_deg': 90.0,
        }])
        augmented, labels, _ = raycast_scene(np.array([[0.0, -10.0, 0.0]]), config)
        np.testing.assert_allclose(augmented[0], [0.0, -3.0, 0.0], atol=1e-12)
        self.assertEqual(labels[0], 0)

    def test_arbitrary_axis_cylinder_and_ellipsoid(self):
        cylinder = base_config([{
            'id': 'pipe', 'shape': 'cylinder', 'center_xyz': [0.0, -5.0, 0.0],
            'axis_xyz': [1.0, 0.0, 0.0], 'radius_m': 0.5, 'length_m': 2.0,
        }])
        cylinder_xyz, _, _ = raycast_scene(np.array([[0.0, -10.0, 0.0]]), cylinder)
        np.testing.assert_allclose(cylinder_xyz[0], [0.0, -4.5, 0.0])

        ellipsoid = base_config([{
            'id': 'bundle', 'shape': 'ellipsoid', 'center_xyz': [0.0, -5.0, 0.0],
            'radii_xyz': [1.0, 2.0, 1.0],
        }])
        ellipsoid_xyz, _, _ = raycast_scene(np.array([[0.0, -10.0, 0.0]]), ellipsoid)
        np.testing.assert_allclose(ellipsoid_xyz[0], [0.0, -3.0, 0.0])

    def test_composite_parts_share_one_object_ground_truth(self):
        config = base_config([{
            'id': 'tool', 'category': 'COMPOSITE_TOOL', 'pose': 'ON_TRACK',
            'parts': [
                {'id': 'near', 'shape': 'box', 'center_xyz': [0.0, -4.0, 0.0],
                 'size_xyz': [1.0, 1.0, 1.0]},
                {'id': 'far', 'shape': 'box', 'center_xyz': [0.0, -7.0, 0.0],
                 'size_xyz': [1.0, 1.0, 1.0]},
            ],
        }])
        augmented, labels, truth = raycast_scene(np.array([[0.0, -10.0, 0.0]]), config)
        np.testing.assert_allclose(augmented[0], [0.0, -3.5, 0.0])
        self.assertEqual(labels[0], 0)
        obstacle = truth['obstacles'][0]
        self.assertEqual(obstacle['shape'], 'composite')
        self.assertEqual(obstacle['parts_count'], 2)
        self.assertEqual(obstacle['synthetic_returns'], 1)
        self.assertEqual([part['synthetic_returns'] for part in obstacle['parts']], [1, 0])

    def test_scenario_selection_supports_cycle_and_explicit_override(self):
        config = base_config()
        config.pop('obstacles')
        config['scenarios'] = [
            {'id': 'near', 'objects': [{
                'id': 'near_box', 'shape': 'box', 'center_xyz': [0.0, -4.0, 0.0],
                'size_xyz': [1.0, 1.0, 1.0]}]},
            {'id': 'far', 'objects': [{
                'id': 'far_box', 'shape': 'box', 'center_xyz': [0.0, -8.0, 0.0],
                'size_xyz': [1.0, 1.0, 1.0]}]},
        ]
        config['scenario_selection'] = {
            'mode': 'cycle', 'frames_per_scenario': 2, 'default_scenario_id': 'near'}
        self.assertEqual(select_scenario(config, frame_index=0)['id'], 'near')
        self.assertEqual(select_scenario(config, frame_index=2)['id'], 'far')
        self.assertEqual(select_scenario(config, scenario_id='far', frame_index=0)['id'], 'far')
        _, _, truth = raycast_scene(
            np.array([[0.0, -20.0, 0.0]]), config, frame_index=2)
        self.assertEqual(truth['scenario_id'], 'far')
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_SCENARIO_ID'):
            raycast_scene(np.array([[0.0, -20.0, 0.0]]), config, scenario_id='missing')

    def test_zero_and_nonfinite_source_returns_are_not_synthetic_rays(self):
        xyz = np.array([[0.0, 0.0, 0.0], [np.nan, -10.0, 0.0]])
        augmented, labels, truth = raycast_scene(xyz, base_config())
        np.testing.assert_allclose(augmented[0], xyz[0])
        self.assertTrue(np.isnan(augmented[1, 0]))
        np.testing.assert_array_equal(labels, [-1, -1])
        self.assertEqual(truth['usable_source_returns'], 0)

    def test_pointcloud_schema_fields_endian_and_padding_are_preserved(self):
        for bigendian in (False, True):
            message = cloud([(0.0, -10.0, 0.0), (3.0, -10.0, 0.0)],
                            bigendian=bigendian)
            original_padding = bytes(message.data[-5:])
            original_view = point_view(message)
            rings = original_view['ring'].copy()
            timestamps = original_view['timestamp'].copy()
            output, truth = augment_pointcloud2(message, base_config(), frame_index=4)
            view = point_view(output)
            np.testing.assert_allclose(
                [view['x'][0, 0], view['y'][0, 0], view['z'][0, 0]], [0.0, -4.0, 0.0])
            self.assertAlmostEqual(float(view['intensity'][0, 0]), 42.0)
            self.assertAlmostEqual(float(view['intensity'][0, 1]), 4.5)
            np.testing.assert_array_equal(view['ring'], rings)
            np.testing.assert_array_equal(view['timestamp'], timestamps)
            self.assertEqual(bytes(output.data[-5:]), original_padding)
            self.assertEqual(message.header.frame_id, output.header.frame_id)
            self.assertAlmostEqual(float(original_view['y'][0, 0]), -10.0)
            self.assertAlmostEqual(float(original_view['intensity'][0, 0]), 3.5)
            self.assertEqual(truth['header_timestamp_ns'], '10000000020')
            self.assertTrue(truth['fields_preserved'])

    def test_frame_mismatch_fails_without_output(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_FRAME_MISMATCH'):
            augment_pointcloud2(cloud([(0.0, -10.0, 0.0)], frame='hesai_lidar'),
                                base_config())

    def test_dropout_is_deterministic_and_marked_as_zero_return(self):
        config = base_config()
        config['dropout_probability'] = 1.0
        xyz = np.array([[0.0, -10.0, 0.0]])
        augmented, labels, truth = raycast_scene(xyz, config, frame_index=8)
        np.testing.assert_allclose(augmented[0], [0.0, 0.0, 0.0])
        self.assertEqual(labels[0], 0)
        self.assertEqual(truth['dropped_synthetic_returns'], 1)
        self.assertEqual(truth['synthetic_returns'], 0)

    def test_invalid_contract_is_rejected(self):
        config = base_config()
        config['target_from_source'] = 'track <- lidar_livox'
        with self.assertRaisesRegex(ValueError, 'identity'):
            validate_synthetic_config(config)

    def test_repository_example_config_is_valid(self):
        import yaml
        with (ROOT / 'config' / 'synthetic_obstacles_development.yaml').open(
                encoding='utf-8') as stream:
            config = yaml.safe_load(stream)
        validate_synthetic_config(config)
        expected = {
            'standing_person', 'lying_person', 'dog_standing', 'dog_lying',
            'suitcase', 'low_box', 'crowbar', 'shovel', 'jacket_bundle',
            'pipe_across_track', 'cable', 'maintenance_trolley',
        }
        self.assertEqual({item['id'] for item in scenario_catalog(config)}, expected)
        self.assertEqual(config['scenario_selection']['mode'], 'cycle')
        for scenario in scenario_catalog(config):
            centres = []
            for obstacle in scenario['objects']:
                primitives = obstacle.get('parts', [obstacle])
                centres.extend(np.asarray(part['center_xyz'], dtype=float) * 2.0
                               for part in primitives)
            _, _, truth = raycast_scene(
                np.asarray(centres), config, scenario_id=scenario['id'])
            self.assertGreater(
                truth['synthetic_returns'], 0,
                f"Scenario {scenario['id']} is not visible on rays through its part centres")


if __name__ == '__main__':
    unittest.main()
