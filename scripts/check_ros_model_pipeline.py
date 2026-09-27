"""Check real ROS2 model output against the existing direct C++ model path.

Run inside the project's Humble image with the workspace mounted read-only.
This checks integration on development data, not independent detector quality.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import time

import numpy as np
import rclpy
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import point_view
from cpu_catalog_runtime import CpuCatalogRuntime, DirectDetailedCpuRuntime, cloud_from_xyz


PARITY_FIELDS = (
    'system_status', 'safety_decision_permitted',
    'noise_filter_mode', 'rail_selection_method', 'rail_search_config',
    'forward_extension_method', 'forward_extrapolated', 'curve_axis_status',
    'raw_core_return_present', 'rail_pair_count', 'observed_rail_pair_count',
    'core_count', 'reportable_core_count', 'ignored_noise_count',
    'margin_count', 'outside_reference_count', 'unknown_count',
    'core_source_indices', 'reportable_core_source_indices',
    'ignored_noise_source_indices', 'margin_source_indices',
    'nearest_reportable_intrusion_source_index',
    'nearest_reportable_intrusion_distance_from_source_origin_m',
    'nearest_reportable_intrusion_xyz', 'core_bounds_source_axis',
    'expanded_bounds_source_axis', 'rail_pairs_source_xyz',
    'core_envelope_wireframe_source_xyz', 'expanded_envelope_wireframe_source_xyz',
)

BASELINE_V3_PARITY_FIELDS = PARITY_FIELDS + (
    'status', 'reason', 'intrusion_candidate_present',
    'reportable_intrusion_candidate_present',
    'baseline_v3_geometry_obstacle_count',
    'baseline_v3_boundary_warning_count',
    'baseline_v3_model_assist_count',
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def receive_cloud(runtime, cloud, timeout=30.0):
    """Publish an actual schema/invalid input without the XYZ viewer adapter."""
    expected_stamp = str(cloud.header.stamp.sec * 1_000_000_000 + cloud.header.stamp.nanosec)
    runtime.received.clear()
    deadline, next_publish = time.monotonic() + timeout, 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_publish:
            runtime.publisher.publish(cloud)
            next_publish = now + 2.0
        rclpy.spin_once(runtime.node, timeout_sec=0.1)
        for result in runtime.received:
            if (result.get('header_timestamp_ns') == expected_stamp and
                    result.get('source_frame') == cloud.header.frame_id):
                return result
    raise TimeoutError('ROS2 node did not return a matching input result')


def check_unknown(result, noise_filter_mode, reason=None):
    require(result['status'] == 'UNKNOWN', 'invalid input must be UNKNOWN')
    require(result['system_status'] == 'UNKNOWN', 'health must remain UNKNOWN')
    require(result['safety_decision_permitted'] is False, 'safety flag changed')
    require(result['intrusion_candidate_present'] is None, 'UNKNOWN must not become false/no-obstacle')
    require(result['reportable_intrusion_candidate_present'] is None, 'UNKNOWN reportable candidate changed')
    require(result['model_frame_intrusion_candidate_present'] is None, 'UNKNOWN retained frame model alarm')
    require(result['model_temporal_confirmed_intrusion_candidate_present'] is None,
            'UNKNOWN retained confirmed model alarm')
    require(result['temporal_confirmation_status'] == 'RESET_UNKNOWN', 'UNKNOWN did not reset temporal state')
    require(result['noise_filter_mode'] == noise_filter_mode, 'UNKNOWN lost model mode')
    require(result['runtime_transport'] == 'ros2', 'not ROS2 output')
    require(result['core_source_indices'] == [], 'UNKNOWN retained stale CORE')
    if reason:
        require(result['reason'] == reason, f'expected {reason}, got {result["reason"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/workspace'))
    parser.add_argument('--frames', type=int, nargs='+',
                        help='optional sparse frame list; default replays the whole extracted development sequence')
    parser.add_argument('--noise-filter-mode', choices=('baseline_v3_assist_score', 'baseline_v3'),
                        default='baseline_v3')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    player = args.root / 'artefacts/stage_2/player_doubleT_obstacle'
    manifest = json.loads((player / 'manifest.json').read_text())
    records = {record['index']: record for record in manifest['frames']}
    frame_indices = args.frames if args.frames else sorted(records)
    ros = CpuCatalogRuntime(rail_forward_min_m=2.0, noise_filter_mode=args.noise_filter_mode)
    direct = None
    checks = []
    try:
        direct = DirectDetailedCpuRuntime(rail_forward_min_m=2.0, noise_filter_mode=args.noise_filter_mode)
        previous_model_alarm = False
        for index in frame_indices:
            record = records[index]
            raw = (player / record['file']).read_bytes()
            expected = direct.analyze(record, raw)
            actual = ros.analyze(record, raw)
            parity_fields = BASELINE_V3_PARITY_FIELDS if args.noise_filter_mode == 'baseline_v3' else PARITY_FIELDS
            different = [key for key in parity_fields if actual.get(key) != expected.get(key)]
            require(not different, f'frame {index}: ROS/direct mismatch {different}')
            require(actual['runtime_transport'] == 'ros2', 'viewer adapter did not use ROS2')
            require(actual['header_timestamp_ns'] == str(record['header_timestamp_ns']), 'stamp changed')
            require(actual['source_frame'] == record['source_frame'], 'frame changed')
            if expected.get('intrusion_candidate_present') is None:
                check_unknown(actual, args.noise_filter_mode)
                previous_model_alarm = False
                checks.append({'frame': index, 'parity_fields': len(PARITY_FIELDS),
                               'model_frame_candidate': None, 'candidate': None,
                               'core_count': actual.get('core_count'),
                               'reportable_core_count': actual.get('reportable_core_count')})
                if args.frames:
                    print(json.dumps(checks[-1]), flush=True)
                continue
            if args.noise_filter_mode == 'baseline_v3':
                model_alarm = expected.get('baseline_v3_model_assist_count', 0) > 0
                geometry_alarm = expected.get('baseline_v3_geometry_obstacle_count', 0) > 0
                boundary_warning = expected.get('baseline_v3_boundary_warning_count', 0) > 0
                require(actual['baseline_v3_model_assist_frame_candidate_present'] is model_alarm,
                        f'frame {index}: baseline_v3 model-assist alarm changed')
                require(actual['baseline_v3_geometry_intrusion_candidate_present'] is geometry_alarm,
                        f'frame {index}: baseline_v3 geometry alarm changed')
                require(actual['baseline_v3_boundary_warning_present'] is boundary_warning,
                        f'frame {index}: baseline_v3 boundary warning changed')
                require(actual['model_frame_intrusion_candidate_present'] is model_alarm,
                        f'frame {index}: generic frame model alarm changed')
                checks.append({'frame': index, 'parity_fields': len(parity_fields),
                               'baseline_v3_geometry_candidate': geometry_alarm,
                               'baseline_v3_model_assist_frame_candidate': model_alarm,
                               'baseline_v3_boundary_warning': boundary_warning,
                               'candidate': actual['intrusion_candidate_present'],
                               'core_count': actual.get('core_count'),
                               'reportable_core_count': actual.get('reportable_core_count')})
                if args.frames or actual['intrusion_candidate_present'] or model_alarm or boundary_warning:
                    print(json.dumps(checks[-1]), flush=True)
                continue
            model_alarm = expected.get('reportable_intrusion_candidate_present') is True
            expected_confirmed = model_alarm and previous_model_alarm
            require(actual['model_frame_intrusion_candidate_present'] is model_alarm,
                    f'frame {index}: ROS raw model alarm changed')
            require(actual['intrusion_candidate_present'] is expected_confirmed,
                    f'frame {index}: temporal candidate changed')
            require(actual['reportable_intrusion_candidate_present'] is expected_confirmed,
                    f'frame {index}: temporal reportable candidate changed')
            require(actual['model_temporal_confirmed_intrusion_candidate_present'] is expected_confirmed,
                    f'frame {index}: confirmed diagnostic mismatch')
            require(actual['temporal_confirmation_enabled'] is True, 'temporal confirmation not enabled')
            require(actual['temporal_required_consecutive_frames'] == 2, 'temporal window changed')
            if model_alarm:
                require(actual['model_temporal_consecutive_alarm_frames'] >= 1,
                        f'frame {index}: missing temporal alarm streak')
            else:
                require(actual['model_temporal_consecutive_alarm_frames'] == 0,
                        f'frame {index}: temporal streak was not reset')
            previous_model_alarm = model_alarm
            checks.append({'frame': index, 'parity_fields': len(PARITY_FIELDS),
                           'model_frame_candidate': actual['model_frame_intrusion_candidate_present'],
                           'candidate': actual['intrusion_candidate_present'],
                           'core_count': actual.get('core_count'),
                           'reportable_core_count': actual.get('reportable_core_count')})
            if args.frames or actual['intrusion_candidate_present'] or actual['model_frame_intrusion_candidate_present']:
                print(json.dumps(checks[-1]), flush=True)

        record = dict(records[13])
        raw = (player / record['file']).read_bytes()
        record['header_timestamp_ns'] = str(int(record['header_timestamp_ns']) + 10)
        # One return cannot support an axis. Keep model identity on this branch.
        missing = ros.analyze(record, raw[:12])
        check_unknown(missing, args.noise_filter_mode)
        # Advance header to prevent a delayed duplicate from matching these inputs.
        record['header_timestamp_ns'] = str(int(record['header_timestamp_ns']) + 1)
        cloud = cloud_from_xyz(record, raw[:12])
        cloud.fields = [field for field in cloud.fields if field.name != 'y']
        check_unknown(receive_cloud(ros, cloud), args.noise_filter_mode, 'UNSUPPORTED_POINTCLOUD_XYZ_SCHEMA')
        cloud.header.stamp.nanosec += 1
        cloud.header.frame_id = 'unexpected_frame'
        check_unknown(receive_cloud(ros, cloud), args.noise_filter_mode, 'UNSUPPORTED_SOURCE_FRAME')
        # Synthetic frame switch checks adapter lifecycle, not Hesai geometry quality.
        switch_record = dict(record, source_frame='hesai_lidar')
        check_unknown(ros.analyze(switch_record, raw[:12]), args.noise_filter_mode)
        check_unknown(ros.analyze(record, raw[:12]), args.noise_filter_mode)

        # Publish an original 26-byte PointCloud2 with ring/timestamp/zero returns,
        # not only the viewer's compact XYZ schema. Existing extracted bag required.
        bag = args.root / 'dataset/extracted/doubleT_obstacle'
        databases = sorted(bag.glob('*.db3'))
        require(bool(databases), f'missing extracted test bag: {bag}')
        with sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('select data from messages order by timestamp,id limit 1 offset 13').fetchone()
        original = deserialize_message(row[0], PointCloud2)
        ros._stop_current_node()
        ros._start_for_source_frame(original.header.frame_id)
        original_first = receive_cloud(ros, original)
        require(original_first['noise_filter_mode'] == args.noise_filter_mode,
                'original bag mode changed')
        if original.header.stamp.nanosec == 999_999_999:
            original.header.stamp.sec += 1
            original.header.stamp.nanosec = 0
        else:
            original.header.stamp.nanosec += 1
        original_result = receive_cloud(ros, original)
        require(original_result['noise_filter_mode'] == args.noise_filter_mode,
                'original bag repeated mode changed')
        view = point_view(original)
        xyz = np.column_stack([view[name].reshape(-1) for name in ('x', 'y', 'z')])
        valid_indices = np.flatnonzero(np.isfinite(xyz).all(axis=1) & np.any(xyz != 0, axis=1))
        compact = xyz[valid_indices].astype('<f4').tobytes()
        reference = direct.analyze(records[13], compact)
        for key in ('core_source_indices', 'reportable_core_source_indices', 'ignored_noise_source_indices'):
            mapped = valid_indices[np.asarray(reference[key], dtype=int)].tolist()
            require(original_result[key] == mapped, f'original schema changed {key}')
        if 'nearest_reportable_intrusion_xyz' in reference:
            require(original_result['nearest_reportable_intrusion_xyz'] == reference['nearest_reportable_intrusion_xyz'],
                    'original bag nearest point differs')
        else:
            require('nearest_reportable_intrusion_xyz' not in original_result,
                    'original bag gained a reportable nearest point')
        summary = {'status': 'PASS', 'runtime_transport': 'ros2', 'noise_filter_mode': args.noise_filter_mode,
                   'forward_extension_method': 'tangent', 'cases': checks,
                   'negative_checks': ['missing_axis', 'missing_y', 'wrong_frame', 'source_switch'],
                   'original_pointcloud_point_step': original.point_step,
                   'original_pointcloud_points': original.width * original.height,
                   'scope': 'DEVELOPMENT_INTEGRATION_PARITY_NOT_INDEPENDENT_QUALITY'}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary), flush=True)
    finally:
        if direct is not None:
            direct.close()
        ros.close()


if __name__ == '__main__':
    main()
