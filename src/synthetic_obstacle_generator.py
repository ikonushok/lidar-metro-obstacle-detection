"""Development-only synthetic obstacle insertion for real PointCloud2 rays.

The generator keeps the original point order and schema.  For every usable
source return it casts the observed sensor ray into a small parametric scene.
An original return is replaced only when the nearest synthetic surface is
closer, which gives deterministic first-return occlusion without inventing a
new scan pattern.

This is a scenario-testing tool.  It does not calibrate frames, model a real
LiDAR intensity response, or provide a safety/CLEAR decision.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time

import numpy as np
import yaml

from cloud_input import point_view


SYNTHETIC_STATUS = 'SYNTHETIC_DEVELOPMENT_ONLY'
NO_HIT = -1


def load_synthetic_config(path):
    with Path(path).open(encoding='utf-8') as stream:
        config = yaml.safe_load(stream)
    validate_synthetic_config(config)
    return config


def _finite_vector(value, name, length=3):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (length,) or not np.isfinite(array).all():
        raise ValueError(f'{name} must contain {length} finite values')
    return array


def _validate_primitive(primitive, name):
    _finite_vector(primitive.get('center_xyz'), f'{name}.center_xyz')
    shape = primitive.get('shape')
    if shape == 'box':
        size = _finite_vector(primitive.get('size_xyz'), f'{name}.size_xyz')
        if np.any(size <= 0):
            raise ValueError(f'{name}.size_xyz must be positive')
        yaw = float(primitive.get('yaw_deg', 0.0))
        if not np.isfinite(yaw):
            raise ValueError(f'{name}.yaw_deg must be finite')
    elif shape == 'cylinder':
        radius = float(primitive.get('radius_m', 0.0))
        length = float(primitive.get('length_m', primitive.get('height_m', 0.0)))
        axis = _finite_vector(primitive.get('axis_xyz', [0.0, 0.0, 1.0]),
                              f'{name}.axis_xyz')
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError(f'{name}.radius_m must be positive')
        if not np.isfinite(length) or length <= 0:
            raise ValueError(f'{name}.length_m/height_m must be positive')
        if np.linalg.norm(axis) <= 1e-12:
            raise ValueError(f'{name}.axis_xyz must be non-zero')
    elif shape == 'ellipsoid':
        radii = _finite_vector(primitive.get('radii_xyz'), f'{name}.radii_xyz')
        if np.any(radii <= 0):
            raise ValueError(f'{name}.radii_xyz must be positive')
        yaw = float(primitive.get('yaw_deg', 0.0))
        if not np.isfinite(yaw):
            raise ValueError(f'{name}.yaw_deg must be finite')
    else:
        raise ValueError(f'{name}.shape must be box, cylinder or ellipsoid')


def _validate_objects(objects, scope):
    if not isinstance(objects, list) or not objects:
        raise ValueError(f'{scope} must contain at least one object')
    identifiers = set()
    for object_index, obstacle in enumerate(objects):
        identifier = obstacle.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError(f'{scope} object ids must be non-empty and unique')
        identifiers.add(identifier)
        parts = obstacle.get('parts')
        if parts is None:
            _validate_primitive(obstacle, identifier)
            continue
        if not isinstance(parts, list) or not parts:
            raise ValueError(f'{identifier}.parts must be a non-empty list')
        part_ids = set()
        for part_index, part in enumerate(parts):
            part_id = part.get('id', f'part_{part_index}')
            if not isinstance(part_id, str) or not part_id or part_id in part_ids:
                raise ValueError(f'{identifier} part ids must be non-empty and unique')
            part_ids.add(part_id)
            _validate_primitive(part, f'{identifier}.{part_id}')


def scenario_catalog(config):
    """Return normalized scenario dictionaries; preserve the legacy flat config."""
    scenarios = config.get('scenarios')
    if scenarios is not None:
        return scenarios
    return [{
        'id': 'legacy_default',
        'label': 'Legacy flat obstacle list',
        'objects': config.get('obstacles'),
    }]


def select_scenario(config, scenario_id=None, frame_index=0):
    """Select an explicit, fixed-default, or deterministic cycle scenario."""
    scenarios = scenario_catalog(config)
    by_id = {scenario['id']: scenario for scenario in scenarios}
    if scenario_id:
        if scenario_id not in by_id:
            raise ValueError(f'UNKNOWN_SCENARIO_ID:{scenario_id}')
        return by_id[scenario_id]
    if 'scenarios' not in config:
        return scenarios[0]
    selection = config.get('scenario_selection', {})
    mode = selection.get('mode', 'fixed')
    if mode == 'cycle':
        frames = int(selection['frames_per_scenario'])
        return scenarios[(int(frame_index) // frames) % len(scenarios)]
    return by_id[selection.get('default_scenario_id', scenarios[0]['id'])]


def validate_synthetic_config(config):
    if not isinstance(config, dict):
        raise ValueError('Synthetic config must be a mapping')
    if config.get('status') != SYNTHETIC_STATUS:
        raise ValueError('Synthetic config status must be SYNTHETIC_DEVELOPMENT_ONLY')
    if config.get('safety_decision_permitted') is not False:
        raise ValueError('Synthetic config must prohibit safety decisions')
    if config.get('clear_decision_permitted') is not False:
        raise ValueError('Synthetic config must prohibit CLEAR decisions')
    source_frame = config.get('source_frame')
    if not isinstance(source_frame, str) or not source_frame:
        raise ValueError('source_frame is required')
    if config.get('target_from_source') != f'{source_frame} <- {source_frame}':
        raise ValueError('Only an explicit source-frame identity contract is supported')
    if config.get('units') != 'm':
        raise ValueError('Only explicitly declared metre coordinates are supported')
    _finite_vector(config.get('sensor_origin_xyz', [0.0, 0.0, 0.0]), 'sensor_origin_xyz')
    minimum_range = float(config.get('minimum_range_m', 0.0))
    epsilon = float(config.get('occlusion_epsilon_m', 1e-6))
    dropout = float(config.get('dropout_probability', 0.0))
    if not np.isfinite(minimum_range) or minimum_range < 0:
        raise ValueError('minimum_range_m must be finite and non-negative')
    if not np.isfinite(epsilon) or epsilon < 0:
        raise ValueError('occlusion_epsilon_m must be finite and non-negative')
    if not np.isfinite(dropout) or not 0.0 <= dropout <= 1.0:
        raise ValueError('dropout_probability must be in [0, 1]')
    intensity = config.get('intensity', {'mode': 'preserve_background'})
    if intensity.get('mode') not in ('preserve_background', 'constant'):
        raise ValueError('intensity.mode must be preserve_background or constant')
    if intensity.get('mode') == 'constant' and not np.isfinite(float(intensity.get('value'))):
        raise ValueError('intensity.value must be finite for constant mode')

    has_flat = config.get('obstacles') is not None
    has_scenarios = config.get('scenarios') is not None
    if has_flat == has_scenarios:
        raise ValueError('Define exactly one of obstacles or scenarios')
    if has_flat:
        _validate_objects(config['obstacles'], 'obstacles')
        return

    scenarios = config['scenarios']
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError('scenarios must be a non-empty list')
    scenario_ids = set()
    for scenario in scenarios:
        identifier = scenario.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in scenario_ids:
            raise ValueError('Scenario ids must be non-empty and unique')
        scenario_ids.add(identifier)
        _validate_objects(scenario.get('objects'), f'scenario {identifier}')
    selection = config.get('scenario_selection', {})
    mode = selection.get('mode', 'fixed')
    if mode not in ('fixed', 'cycle'):
        raise ValueError('scenario_selection.mode must be fixed or cycle')
    default_id = selection.get('default_scenario_id', scenarios[0]['id'])
    if default_id not in scenario_ids:
        raise ValueError('scenario_selection.default_scenario_id is unknown')
    if mode == 'cycle' and int(selection.get('frames_per_scenario', 0)) <= 0:
        raise ValueError('cycle mode requires positive frames_per_scenario')


def _oriented_box_hit_distance(origin, directions, obstacle, minimum_range):
    center = _finite_vector(obstacle['center_xyz'], 'center_xyz')
    half_size = _finite_vector(obstacle['size_xyz'], 'size_xyz') / 2.0
    yaw = np.deg2rad(float(obstacle.get('yaw_deg', 0.0)))
    cosine, sine = np.cos(yaw), np.sin(yaw)

    relative = origin - center
    local_origin = np.array([
        cosine * relative[0] + sine * relative[1],
        -sine * relative[0] + cosine * relative[1],
        relative[2],
    ])
    local_direction = np.column_stack((
        cosine * directions[:, 0] + sine * directions[:, 1],
        -sine * directions[:, 0] + cosine * directions[:, 1],
        directions[:, 2],
    ))

    near = np.full(len(directions), -np.inf, dtype=np.float64)
    far = np.full(len(directions), np.inf, dtype=np.float64)
    possible = np.ones(len(directions), dtype=bool)
    for axis in range(3):
        component = local_direction[:, axis]
        parallel = np.abs(component) <= 1e-12
        possible &= ~(parallel & (np.abs(local_origin[axis]) > half_size[axis]))
        active = ~parallel
        first = np.full(len(directions), -np.inf, dtype=np.float64)
        second = np.full(len(directions), np.inf, dtype=np.float64)
        first[active] = (-half_size[axis] - local_origin[axis]) / component[active]
        second[active] = (half_size[axis] - local_origin[axis]) / component[active]
        axis_near = np.minimum(first, second)
        axis_far = np.maximum(first, second)
        near = np.maximum(near, axis_near)
        far = np.minimum(far, axis_far)
    candidate = np.where(near >= minimum_range, near, far)
    valid = possible & (far >= near) & (candidate >= minimum_range)
    return np.where(valid, candidate, np.inf)


def _cylinder_hit_distance(origin, directions, obstacle, minimum_range):
    center = _finite_vector(obstacle['center_xyz'], 'center_xyz')
    radius = float(obstacle['radius_m'])
    half_length = float(obstacle.get('length_m', obstacle.get('height_m'))) / 2.0
    axis = _finite_vector(obstacle.get('axis_xyz', [0.0, 0.0, 1.0]), 'axis_xyz')
    axis /= np.linalg.norm(axis)
    relative = origin - center
    candidates = np.full((len(directions), 4), np.inf, dtype=np.float64)

    relative_parallel = float(relative @ axis)
    direction_parallel = directions @ axis
    relative_perpendicular = relative - relative_parallel * axis
    direction_perpendicular = directions - direction_parallel[:, None] * axis
    a = np.einsum('ij,ij->i', direction_perpendicular, direction_perpendicular)
    b = 2.0 * (direction_perpendicular @ relative_perpendicular)
    c = float(relative_perpendicular @ relative_perpendicular) - radius ** 2
    discriminant = b ** 2 - 4.0 * a * c
    has_side = (a > 1e-12) & (discriminant >= 0.0)
    root = np.zeros(len(directions), dtype=np.float64)
    root[has_side] = np.sqrt(discriminant[has_side])
    for column, sign in enumerate((-1.0, 1.0)):
        distance = np.full(len(directions), np.inf, dtype=np.float64)
        distance[has_side] = (-b[has_side] + sign * root[has_side]) / (2.0 * a[has_side])
        safe_distance = np.where(np.isfinite(distance), distance, 0.0)
        axial = relative_parallel + safe_distance * direction_parallel
        valid = has_side & (distance >= minimum_range) & (np.abs(axial) <= half_length + 1e-9)
        candidates[:, column] = np.where(valid, distance, np.inf)

    crosses_caps = np.abs(direction_parallel) > 1e-12
    for column, cap_position in enumerate((-half_length, half_length), start=2):
        distance = np.full(len(directions), np.inf, dtype=np.float64)
        distance[crosses_caps] = (
            (cap_position - relative_parallel) / direction_parallel[crosses_caps])
        safe_distance = np.where(np.isfinite(distance), distance, 0.0)
        radial = relative_perpendicular + safe_distance[:, None] * direction_perpendicular
        radial_squared = np.einsum('ij,ij->i', radial, radial)
        valid = (crosses_caps & (distance >= minimum_range) &
                 (radial_squared <= radius ** 2 + 1e-9))
        candidates[:, column] = np.where(valid, distance, np.inf)
    return candidates.min(axis=1)


def _ellipsoid_hit_distance(origin, directions, obstacle, minimum_range):
    center = _finite_vector(obstacle['center_xyz'], 'center_xyz')
    radii = _finite_vector(obstacle['radii_xyz'], 'radii_xyz')
    yaw = np.deg2rad(float(obstacle.get('yaw_deg', 0.0)))
    cosine, sine = np.cos(yaw), np.sin(yaw)
    relative = origin - center
    local_origin = np.array([
        cosine * relative[0] + sine * relative[1],
        -sine * relative[0] + cosine * relative[1],
        relative[2],
    ]) / radii
    local_direction = np.column_stack((
        cosine * directions[:, 0] + sine * directions[:, 1],
        -sine * directions[:, 0] + cosine * directions[:, 1],
        directions[:, 2],
    )) / radii
    a = np.einsum('ij,ij->i', local_direction, local_direction)
    b = 2.0 * (local_direction @ local_origin)
    c = float(local_origin @ local_origin) - 1.0
    discriminant = b ** 2 - 4.0 * a * c
    possible = (a > 1e-12) & (discriminant >= 0.0)
    root = np.zeros(len(directions), dtype=np.float64)
    root[possible] = np.sqrt(discriminant[possible])
    near = np.full(len(directions), np.inf, dtype=np.float64)
    far = np.full(len(directions), np.inf, dtype=np.float64)
    near[possible] = (-b[possible] - root[possible]) / (2.0 * a[possible])
    far[possible] = (-b[possible] + root[possible]) / (2.0 * a[possible])
    candidate = np.where(near >= minimum_range, near, far)
    return np.where(possible & (candidate >= minimum_range), candidate, np.inf)


def _primitive_hit_distance(origin, directions, primitive, minimum_range):
    if primitive['shape'] == 'box':
        return _oriented_box_hit_distance(origin, directions, primitive, minimum_range)
    if primitive['shape'] == 'cylinder':
        return _cylinder_hit_distance(origin, directions, primitive, minimum_range)
    return _ellipsoid_hit_distance(origin, directions, primitive, minimum_range)


def _expanded_parts(objects):
    expanded = []
    for object_index, obstacle in enumerate(objects):
        parts = obstacle.get('parts')
        if parts is None:
            expanded.append((object_index, obstacle.get('id', f'object_{object_index}'), obstacle))
            continue
        for part_index, part in enumerate(parts):
            expanded.append((object_index, part.get('id', f'part_{part_index}'), part))
    return expanded


def raycast_scene(xyz, config, frame_index=0, scenario_id=None):
    """Return augmented XYZ, per-point obstacle labels, and compact ground truth."""
    validate_synthetic_config(config)
    xyz = np.asarray(xyz)
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError('xyz must have shape (N, 3)')
    output = np.array(xyz, dtype=np.float64, copy=True)
    scenario = select_scenario(config, scenario_id=scenario_id, frame_index=frame_index)
    objects = scenario['objects']
    parts = _expanded_parts(objects)
    origin = _finite_vector(config.get('sensor_origin_xyz', [0.0, 0.0, 0.0]),
                            'sensor_origin_xyz')
    relative = output - origin
    ranges = np.linalg.norm(relative, axis=1)
    usable = np.isfinite(output).all(axis=1) & np.isfinite(ranges) & (ranges > 0.0)
    usable_indices = np.flatnonzero(usable)
    labels = np.full(len(output), NO_HIT, dtype=np.int32)
    part_labels = np.full(len(output), NO_HIT, dtype=np.int32)
    best_distance = np.full(len(usable_indices), np.inf, dtype=np.float64)
    best_obstacle = np.full(len(usable_indices), NO_HIT, dtype=np.int32)
    best_part = np.full(len(usable_indices), NO_HIT, dtype=np.int32)
    directions = relative[usable] / ranges[usable, None]
    minimum_range = float(config.get('minimum_range_m', 0.0))

    for part_index, (obstacle_index, _, primitive) in enumerate(parts):
        hit_distance = _primitive_hit_distance(
            origin, directions, primitive, minimum_range)
        nearer = hit_distance < best_distance
        best_distance[nearer] = hit_distance[nearer]
        best_obstacle[nearer] = obstacle_index
        best_part[nearer] = part_index

    epsilon = float(config.get('occlusion_epsilon_m', 1e-6))
    visible = ((best_obstacle != NO_HIT) & np.isfinite(best_distance) &
               (best_distance < ranges[usable] - epsilon))
    visible_global = usable_indices[visible]
    labels[visible_global] = best_obstacle[visible]
    part_labels[visible_global] = best_part[visible]
    output[visible_global] = origin + directions[visible] * best_distance[visible, None]

    dropout_probability = float(config.get('dropout_probability', 0.0))
    dropped = np.zeros(len(output), dtype=bool)
    if dropout_probability > 0.0 and len(visible_global):
        seed = int(config.get('random_seed', 0)) + int(frame_index) * 1_000_003
        random = np.random.default_rng(seed)
        dropped_visible = random.random(len(visible_global)) < dropout_probability
        dropped[visible_global[dropped_visible]] = True
        output[dropped] = 0.0

    obstacle_reports = []
    for obstacle_index, obstacle in enumerate(objects):
        intersections = labels == obstacle_index
        returned = intersections & ~dropped
        distances = np.linalg.norm(output[returned] - origin, axis=1)
        report = {
            'id': obstacle['id'],
            'category': obstacle.get('category', 'UNSPECIFIED'),
            'pose': obstacle.get('pose'),
            'shape': 'composite' if obstacle.get('parts') is not None else obstacle['shape'],
            'parts_count': len(obstacle.get('parts', [obstacle])),
            'ray_intersections_before_dropout': int(intersections.sum()),
            'synthetic_returns': int(returned.sum()),
            'dropped_returns': int((intersections & dropped).sum()),
            'nearest_return_m': float(distances.min()) if len(distances) else None,
            'visible_bounds_xyz': None,
            'parts': [],
        }
        if returned.any():
            points = output[returned]
            report['visible_bounds_xyz'] = {
                axis: {'min': float(points[:, index].min()),
                       'max': float(points[:, index].max())}
                for index, axis in enumerate('xyz')
            }
        for part_index, (owner_index, part_id, primitive) in enumerate(parts):
            if owner_index != obstacle_index:
                continue
            part_intersections = part_labels == part_index
            part_returned = part_intersections & ~dropped
            report['parts'].append({
                'id': part_id,
                'shape': primitive['shape'],
                'ray_intersections_before_dropout': int(part_intersections.sum()),
                'synthetic_returns': int(part_returned.sum()),
                'dropped_returns': int((part_intersections & dropped).sum()),
            })
        obstacle_reports.append(report)

    ground_truth = {
        'status': SYNTHETIC_STATUS,
        'frame_index': int(frame_index),
        'scenario_id': scenario['id'],
        'scenario_label': scenario.get('label', scenario['id']),
        'source_frame': config['source_frame'],
        'target_from_source': config['target_from_source'],
        'units': config['units'],
        'input_points': int(len(output)),
        'usable_source_returns': int(usable.sum()),
        'synthetic_ray_intersections': int((labels != NO_HIT).sum()),
        'synthetic_returns': int(((labels != NO_HIT) & ~dropped).sum()),
        'dropped_synthetic_returns': int(dropped.sum()),
        'obstacles': obstacle_reports,
        'safety_decision_permitted': False,
        'clear_decision_permitted': False,
        'limitations': [
            'OBSERVED_RETURN_RAYS_ONLY',
            'NO_DESKEW_OR_INTRA_SCAN_OBJECT_MOTION',
            'INTENSITY_NOT_PHYSICALLY_MODELLED',
            'NOT_REAL_WORLD_RECALL_EVIDENCE',
        ],
    }
    return output, labels, ground_truth


def augment_pointcloud2(message, config, frame_index=0, scenario_id=None):
    """Copy and augment one PointCloud2-like object without changing its schema."""
    validate_synthetic_config(config)
    if message.header.frame_id != config['source_frame']:
        raise ValueError(
            f"SOURCE_FRAME_MISMATCH:{message.header.frame_id}!={config['source_frame']}")
    output_message = copy.deepcopy(message)
    output_message.data = bytearray(message.data)
    points = point_view(output_message)
    xyz = np.column_stack([points[axis].ravel() for axis in ('x', 'y', 'z')])
    augmented, labels, ground_truth = raycast_scene(
        xyz, config, frame_index=frame_index, scenario_id=scenario_id)
    shape = (message.height, message.width)
    for index, axis in enumerate(('x', 'y', 'z')):
        points[axis][...] = augmented[:, index].reshape(shape)

    synthetic = labels != NO_HIT
    dropped = synthetic & np.all(augmented == 0.0, axis=1)
    intensity_config = config.get('intensity', {'mode': 'preserve_background'})
    if 'intensity' in points.dtype.names and intensity_config.get('mode') == 'constant':
        intensity = points['intensity']
        flat = np.array(intensity, copy=True).reshape(-1)
        flat[synthetic & ~dropped] = float(intensity_config['value'])
        flat[dropped] = 0.0
        intensity[...] = flat.reshape(shape)
        ground_truth['intensity_mode'] = 'CONSTANT_SYNTHETIC_NOT_SENSOR_CALIBRATED'
    else:
        ground_truth['intensity_mode'] = 'PRESERVED_BACKGROUND_NOT_PHYSICALLY_MODELLED'
    ground_truth.update({
        'header_timestamp_ns': str(
            message.header.stamp.sec * 10**9 + message.header.stamp.nanosec),
        'point_step': int(message.point_step),
        'row_step': int(message.row_step),
        'is_bigendian': bool(message.is_bigendian),
        'fields_preserved': True,
        'header_preserved': True,
    })
    return output_message, ground_truth


def synthetic_node_class():
    """Load ROS dependencies only for the streaming wrapper."""
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import PointCloud2
    from std_msgs.msg import String

    class SyntheticObstacleNode(Node):
        def __init__(self, config_path=None, input_topic=None, output_topic=None,
                     ground_truth_topic=None, scenario_id=None):
            super().__init__('synthetic_obstacle_generator')
            self.declare_parameter(
                'config_path', config_path or '/app/config/synthetic_obstacles_development.yaml')
            self.declare_parameter(
                'input_topic', input_topic or '/sensing/lidar/hesai128/pointcloud')
            self.declare_parameter(
                'output_topic', output_topic or '/synthetic/pointcloud')
            self.declare_parameter(
                'ground_truth_topic', ground_truth_topic or '/synthetic/ground_truth')
            self.declare_parameter('scenario_id', scenario_id or '')
            self.config = load_synthetic_config(self.get_parameter('config_path').value)
            self.scenario_id = self.get_parameter('scenario_id').value or None
            self.frame_index = 0
            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.VOLATILE)
            self.cloud_publisher = self.create_publisher(
                PointCloud2, self.get_parameter('output_topic').value, qos)
            self.ground_truth_publisher = self.create_publisher(
                String, self.get_parameter('ground_truth_topic').value, qos)
            self.subscription = self.create_subscription(
                PointCloud2, self.get_parameter('input_topic').value, self.receive, qos)

        def receive(self, message):
            started = time.perf_counter()
            try:
                output, ground_truth = augment_pointcloud2(
                    message, self.config, frame_index=self.frame_index,
                    scenario_id=self.scenario_id)
            except (KeyError, TypeError, ValueError) as error:
                ground_truth = {
                    'status': 'SYNTHETIC_GENERATION_ERROR',
                    'reason': str(error),
                    'frame_index': self.frame_index,
                    'source_frame': message.header.frame_id,
                    'safety_decision_permitted': False,
                    'clear_decision_permitted': False,
                }
            else:
                self.cloud_publisher.publish(output)
            ground_truth['processing_ms'] = (time.perf_counter() - started) * 1000.0
            result = String()
            result.data = json.dumps(ground_truth, ensure_ascii=False, sort_keys=True)
            self.ground_truth_publisher.publish(result)
            self.frame_index += 1

    return SyntheticObstacleNode


def run_node(args):
    import rclpy

    rclpy.init()
    node = synthetic_node_class()(
        config_path=str(args.config), input_topic=args.input_topic,
        output_topic=args.output_topic, ground_truth_topic=args.ground_truth_topic,
        scenario_id=args.scenario_id)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path('/app/config/synthetic_obstacles_development.yaml'))
    parser.add_argument('--input-topic', default='/sensing/lidar/hesai128/pointcloud')
    parser.add_argument('--output-topic', default='/synthetic/pointcloud')
    parser.add_argument('--ground-truth-topic', default='/synthetic/ground_truth')
    parser.add_argument('--scenario-id', default='',
                        help='Fix one scenario; empty uses scenario_selection from YAML')
    parser.add_argument('--validate-config', action='store_true')
    args = parser.parse_args()
    if args.validate_config:
        config = load_synthetic_config(args.config)
        scenarios = scenario_catalog(config)
        print(json.dumps({
            'status': config['status'],
            'scenarios': len(scenarios),
            'objects': sum(len(item['objects']) for item in scenarios),
            'parts': sum(len(_expanded_parts(item['objects'])) for item in scenarios),
        }, sort_keys=True))
        return
    run_node(args)


if __name__ == '__main__':
    main()
