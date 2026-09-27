"""Collect CPU node results for saved XYZ frames and prepare a static viewer dataset."""

import argparse
import json
from pathlib import Path
import shutil
import signal
import subprocess
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import String


def cloud_from_xyzf(path: Path, header_timestamp_ns: str) -> PointCloud2:
    data = path.read_bytes()
    if not data or len(data) % 12:
        raise ValueError(f'{path} must contain non-empty float32 XYZ triplets')
    timestamp_ns = int(header_timestamp_ns)
    cloud = PointCloud2()
    cloud.header.frame_id = 'hesai_lidar'
    cloud.header.stamp.sec = timestamp_ns // 1_000_000_000
    cloud.header.stamp.nanosec = timestamp_ns % 1_000_000_000
    cloud.height = 1
    cloud.width = len(data) // 12
    cloud.is_bigendian = False
    cloud.is_dense = True
    cloud.point_step = 12
    cloud.row_step = cloud.width * cloud.point_step
    cloud.fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    cloud.data = data
    return cloud


def source_records(frames_dir: Path):
    records = {}
    for line in (frames_dir / 'frames.jsonl').read_text(encoding='utf-8').splitlines():
        record = json.loads(line)
        records[int(record['index'])] = record
    return records


def copy_viewer_assets(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile('/app/web/stage_4_cpu_viewer.html', output / 'index.html')
    vendor = output / 'vendor'
    vendor.mkdir(exist_ok=True)
    for source, destination in [
        ('/usr/share/javascript/three/three.min.js', vendor / 'three.min.js'),
        ('/usr/share/javascript/three/examples/js/controls/OrbitControls.js', vendor / 'OrbitControls.js'),
    ]:
        if not Path(source).is_file():
            raise FileNotFoundError(source)
        shutil.copyfile(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frames_dir', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--first-index', type=int)
    parser.add_argument('--last-index', type=int)
    parser.add_argument('--rail-selection-method', choices=('baseline', 'development_candidate'), default='development_candidate')
    args = parser.parse_args()
    source = source_records(args.frames_dir)
    if args.first_index is None:
        args.first_index = min(source)
    if args.last_index is None:
        args.last_index = max(source)
    indexes = [index for index in sorted(source) if args.first_index <= index <= args.last_index]
    if not indexes:
        raise ValueError('no selected source frame records')

    process = subprocess.Popen([
        'ros2', 'run', 'lidar_mosmetro3d_cpp', 'curve_envelope_node', '--ros-args',
        '-p', 'input_topic:=/viewer/cloud', '-p', 'output_topic:=/viewer/candidate',
        '-p', 'source_frame:=hesai_lidar', '-p', 'compute_backend:=cpu',
        '-p', f'rail_selection_method:={args.rail_selection_method}',
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    rclpy.init()
    node = rclpy.create_node('cpu_viewer_export')
    received = []
    publisher = node.create_publisher(PointCloud2, '/viewer/cloud', qos_profile_sensor_data)
    node.create_subscription(String, '/viewer/candidate', lambda message: received.append(json.loads(message.data)), 10)
    try:
        frames, results = [], []
        target_frames = args.output / 'frames'
        target_frames.mkdir(parents=True, exist_ok=True)
        first_offset = float(source[indexes[0]]['bag_offset_seconds'])
        for display_index, source_index in enumerate(indexes):
            record = source[source_index]
            source_file = args.frames_dir / f'frame_{source_index:05d}.xyzf'
            cloud = cloud_from_xyzf(source_file, str(record['header_timestamp_ns']))
            deadline = time.monotonic() + 10.0
            result = None
            while time.monotonic() < deadline:
                publisher.publish(cloud)
                rclpy.spin_once(node, timeout_sec=0.1)
                matches = [item for item in received if item.get('header_timestamp_ns') == str(record['header_timestamp_ns'])]
                if matches:
                    result = matches[-1]
                    break
            if result is None:
                raise TimeoutError(f'no CPU result for source frame {source_index}')
            if result.get('source_frame') != record['input']['frame']:
                raise ValueError('CPU result source frame does not match source record')
            if result.get('safety_decision_permitted') is not False:
                raise ValueError('viewer input must remain candidate-only')
            if result.get('rail_selection_method') != args.rail_selection_method:
                raise ValueError('viewer result rail selection method does not match request')
            filename = f'frame_{display_index:04d}.xyzf'
            shutil.copyfile(source_file, target_frames / filename)
            frames.append({
                'index': display_index,
                'source_index': source_index,
                'file': 'frames/' + filename,
                'displayed_points': cloud.width,
                'header_timestamp_ns': str(record['header_timestamp_ns']),
                'source_frame': record['input']['frame'],
                'bag_offset_seconds': float(record['bag_offset_seconds']) - first_offset,
            })
            results.append(result)
        copy_viewer_assets(args.output)
        manifest = {
            'format': 'lidar-cpu-viewer-v1',
            'dataset': 'new_data saved development frames',
            'safety_decision_permitted': False,
            'compute_backend': 'cpu',
            'rail_selection_method': args.rail_selection_method,
            'frames': frames,
        }
        (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        (args.output / 'results.json').write_text(json.dumps(results, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'frames': len(frames), 'status': [item['status'] for item in results],
                          'backend': 'cpu', 'rail_selection_method': args.rail_selection_method,
                          'output': str(args.output)}, ensure_ascii=False))
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    raise SystemExit(main())
