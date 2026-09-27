"""Replay selected raw bag frames through existing C++ baseline and candidate.

An offline Stage-5 screen only: it does not select rails itself, calibrate the
source coordinates, or turn its results into obstacle decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import String

from cloud_input import inspect_cloud


METHODS = ('baseline', 'development_candidate')


def source_cloud(xyz, header_ns):
    data = xyz.astype('<f4', copy=False).tobytes()
    cloud = PointCloud2()
    cloud.header.frame_id = 'hesai_lidar'
    cloud.header.stamp.sec = header_ns // 1_000_000_000
    cloud.header.stamp.nanosec = header_ns % 1_000_000_000
    cloud.height, cloud.width = 1, len(xyz)
    cloud.is_bigendian, cloud.is_dense = False, True
    cloud.point_step, cloud.row_step = 12, len(data)
    cloud.fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    cloud.data = data
    return cloud, data


def load_frames(bag: Path, indices: list[int]):
    databases = list(bag.glob('*.db3'))
    if len(databases) != 1:
        raise ValueError('Expected exactly one .db3 in bag directory')
    connection = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    try:
        total = connection.execute('select count(*) from messages').fetchone()[0]
        topic_types = {row[0]: (row[2], row[3]) for row in connection.execute(
            'select id,name,type,serialization_format from topics')}
        frames = []
        for index in indices:
            row = connection.execute(
                'select id,topic_id,timestamp,data from messages order by timestamp,id '
                'limit 1 offset ?', (index,)).fetchone()
            if row is None:
                raise IndexError('Bag does not contain frame %d' % index)
            _rowid, topic_id, bag_ns, data = row
            if topic_types[topic_id] != ('sensor_msgs/msg/PointCloud2', 'cdr'):
                raise ValueError('Unsupported topic type at frame %d' % index)
            stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
            frames.append({'index': index, 'bag_timestamp_ns': str(bag_ns), 'stats': stats, 'xyz': xyz})
        return total, frames
    finally:
        connection.close()


def replay(frames, method):
    process = subprocess.Popen([
        'ros2', 'run', 'lidar_mosmetro3d_cpp', 'curve_envelope_node', '--ros-args',
        '-p', 'input_topic:=/stage_5_bag_screen/cloud',
        '-p', 'output_topic:=/stage_5_bag_screen/' + method,
        '-p', 'source_frame:=hesai_lidar', '-p', 'compute_backend:=cpu',
        '-p', 'rail_selection_method:=' + method,
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    node = rclpy.create_node('stage_5_bag_screen_' + method)
    received = []
    publisher = node.create_publisher(PointCloud2, '/stage_5_bag_screen/cloud', qos_profile_sensor_data)
    node.create_subscription(String, '/stage_5_bag_screen/' + method,
                             lambda message: received.append(json.loads(message.data)), 10)
    try:
        output = []
        for frame in frames:
            cloud, raw = source_cloud(frame['xyz'], int(frame['stats']['header_ns']))
            deadline = time.monotonic() + 20.0
            result = None
            while time.monotonic() < deadline:
                publisher.publish(cloud)
                rclpy.spin_once(node, timeout_sec=.1)
                matches = [item for item in received if item.get('header_timestamp_ns') == str(frame['stats']['header_ns'])]
                if matches:
                    result = matches[-1]
                    break
            if result is None:
                raise TimeoutError('No C++ %s result for bag frame %d' % (method, frame['index']))
            if result.get('rail_selection_method') != method or result.get('safety_decision_permitted') is not False:
                raise ValueError('C++ output contract mismatch for frame %d' % frame['index'])
            labelled = (sum(int(result.get(name, 0)) for name in
                            ('core_count', 'margin_count', 'outside_reference_count', 'unknown_count'))
                        if result.get('curve_axis_status') == 'CURVE_AXIS_SUPPORTED'
                        else int(result.get('point_count', 0)))
            if labelled != cloud.width:
                raise ValueError('C++ raw point total mismatch for frame %d' % frame['index'])
            output.append({'index': frame['index'], 'header_timestamp_ns': str(frame['stats']['header_ns']),
                           'raw_xyzf_sha256': hashlib.sha256(raw).hexdigest(),
                           'input': {key: frame['stats'][key] for key in ('points', 'finite', 'zero', 'nonfinite', 'nonzero_finite')},
                           'cpp': result})
        return output
    finally:
        node.destroy_node()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stride', type=int, default=25)
    args = parser.parse_args()
    if args.output.exists() or args.stride <= 0:
        parser.error('Output must not exist and --stride must be positive')
    databases = list(args.bag.glob('*.db3'))
    if len(databases) != 1:
        parser.error('Expected exactly one .db3 in bag directory')
    connection = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    try:
        count = connection.execute('select count(*) from messages').fetchone()[0]
    finally:
        connection.close()
    indices = list(range(0, count, args.stride))
    if indices[-1] != count - 1:
        indices.append(count - 1)
    total, frames = load_frames(args.bag, indices)
    args.output.mkdir(parents=True)
    rclpy.init()
    try:
        methods = {method: replay(frames, method) for method in METHODS}
    finally:
        rclpy.shutdown()
    manifest = {
        'format': 'stage_5_cpp_bag_screen_v1', 'scope': 'STRATIFIED_CONNECTED_BAG_SCREEN_NOT_GROUND_TRUTH',
        'bag': str(args.bag), 'database_messages': total, 'selected_indices': indices,
        'selection_rule': 'every %dth bag message plus final message' % args.stride,
        'input_export': 'finite nonzero XYZ only; zero placeholders excluded and counted per frame',
        'methods': methods, 'safety_decision_permitted': False,
        'limitations': ['No calibrated frame or units', 'No independent rail marks',
                        'Bag name is not evidence of a switch', 'UNKNOWN_NEVER_MEANS_CLEAR'],
    }
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({method: {'frames': len(rows), 'supported': sum(
        item['cpp'].get('curve_axis_status') == 'CURVE_AXIS_SUPPORTED' for item in rows)}
        for method, rows in methods.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
