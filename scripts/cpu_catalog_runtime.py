"""One-frame CPU CurveRailAxis execution for the lazy new_data catalog."""

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import struct
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import String


def cloud_from_xyz(record, xyz_bytes):
    if not xyz_bytes or len(xyz_bytes) % 12:
        raise ValueError('source XYZ must be non-empty float32 triples')
    stamp_ns = int(record['header_timestamp_ns'])
    cloud = PointCloud2()
    cloud.header.frame_id = record['source_frame']
    cloud.header.stamp.sec = stamp_ns // 1_000_000_000
    cloud.header.stamp.nanosec = stamp_ns % 1_000_000_000
    cloud.height = 1
    cloud.width = len(xyz_bytes) // 12
    cloud.is_bigendian = False
    cloud.is_dense = True
    cloud.point_step = 12
    cloud.row_step = cloud.width * cloud.point_step
    cloud.fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    cloud.data = xyz_bytes
    return cloud


class CpuCatalogRuntime:
    """Publishes one raw frame and waits for the matching CPU node JSON."""

    def __init__(self, rail_selection_method='development_candidate', *, rail_forward_min_m=2.0,
                 rail_forward_max_m=80.0, rail_station_length_m=2.0, rail_cell_width_m=0.04,
                 forward_extension_method='tangent', arc_extension_horizon_m=0.0,
                 min_arc_radius_m=60.0, max_arc_turn_deg=8.0, arc_fit_window_pairs=5,
                 noise_filter_mode='baseline_v3'):
        if rail_selection_method not in {'baseline', 'development_candidate'}:
            raise ValueError('unsupported rail selection method')
        if noise_filter_mode not in {'legacy', 'baseline_v3_assist_score', 'baseline_v3'}:
            raise ValueError('unsupported noise filter mode')
        self.noise_filter_mode = noise_filter_mode
        self.runtime_transport = 'ros2'
        values = (rail_forward_min_m, rail_forward_max_m, rail_station_length_m, rail_cell_width_m,
                  arc_extension_horizon_m, min_arc_radius_m, max_arc_turn_deg)
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise ValueError('rail search parameters must be finite numbers')
        if rail_forward_min_m < 0 or rail_forward_max_m <= rail_forward_min_m:
            raise ValueError('invalid rail forward range')
        if rail_station_length_m <= 0 or rail_cell_width_m <= 0:
            raise ValueError('rail station length and cell width must be positive')
        if forward_extension_method not in {'tangent', 'arc_limited', 'arc_clamped'}:
            raise ValueError('unsupported forward extension method')
        if arc_extension_horizon_m < 0 or min_arc_radius_m <= 0 or max_arc_turn_deg <= 0:
            raise ValueError('arc extension parameters must be nonnegative/positive')
        if not isinstance(arc_fit_window_pairs, int) or arc_fit_window_pairs < 3:
            raise ValueError('arc fit window must be an integer >= 3')
        self.rail_selection_method = rail_selection_method
        self.rail_search_config = {
            'forward_min_m': float(rail_forward_min_m),
            'forward_max_m': float(rail_forward_max_m),
            'station_length_m': float(rail_station_length_m),
            'cell_width_m': float(rail_cell_width_m),
        }
        self.forward_extension_config = {
            'method': forward_extension_method,
            'arc_horizon_m': float(arc_extension_horizon_m),
            'min_arc_radius_m': float(min_arc_radius_m),
            'max_arc_turn_deg': float(max_arc_turn_deg),
            'arc_fit_window_pairs': int(arc_fit_window_pairs),
        }
        topic_prefix = f'/cpu_catalog/{self.rail_selection_method}'
        rclpy.init()
        self.topic_prefix = topic_prefix
        self.process = None
        self.node = None
        self.publisher = None
        self.source_frame = None
        self.received = []

    def _start_for_source_frame(self, source_frame):
        cloud_topic = f'{self.topic_prefix}/cloud'
        candidate_topic = f'{self.topic_prefix}/candidate'
        self.process = subprocess.Popen([
            'ros2', 'run', 'lidar_mosmetro3d_cpp', 'curve_envelope_node', '--ros-args',
            '-p', f'input_topic:={cloud_topic}', '-p', f'output_topic:={candidate_topic}',
            '-p', f'source_frame:={source_frame}', '-p', 'compute_backend:=cpu',
            '-p', f'noise_filter_mode:={self.noise_filter_mode}',
            '-p', f'rail_selection_method:={self.rail_selection_method}',
            '-p', f'rail_forward_min_m:={self.rail_search_config["forward_min_m"]}',
            '-p', f'rail_forward_max_m:={self.rail_search_config["forward_max_m"]}',
            '-p', f'rail_station_length_m:={self.rail_search_config["station_length_m"]}',
            '-p', f'rail_cell_width_m:={self.rail_search_config["cell_width_m"]}',
            '-p', f'forward_extension_method:={self.forward_extension_config["method"]}',
            '-p', f'arc_extension_horizon_m:={self.forward_extension_config["arc_horizon_m"]}',
            '-p', f'min_arc_radius_m:={self.forward_extension_config["min_arc_radius_m"]}',
            '-p', f'max_arc_turn_deg:={self.forward_extension_config["max_arc_turn_deg"]}',
            '-p', f'arc_fit_window_pairs:={self.forward_extension_config["arc_fit_window_pairs"]}',
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.node = rclpy.create_node('cpu_catalog_runtime')
        self.publisher = self.node.create_publisher(PointCloud2, cloud_topic, qos_profile_sensor_data)
        self.node.create_subscription(String, candidate_topic,
                                      lambda message: self.received.append(json.loads(message.data)), 10)
        self.source_frame = source_frame
        discovery_deadline = time.monotonic() + 5.0
        while time.monotonic() < discovery_deadline:
            if self.publisher.get_subscription_count() > 0 and self.node.count_publishers(candidate_topic) > 0:
                break
            rclpy.spin_once(self.node, timeout_sec=0.1)

    def _stop_current_node(self):
        if self.node is not None:
            self.node.destroy_node()
            self.node = None
            self.publisher = None
        if self.process is not None and self.process.poll() is None:
            if os.name == 'posix':
                os.killpg(self.process.pid, signal.SIGTERM)
            else:
                self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(self.process.pid, signal.SIGKILL)
                else:
                    self.process.kill()
        self.process = None
        self.source_frame = None
        self.received.clear()

    def analyze(self, record, xyz_bytes, timeout_seconds=30.0):
        cloud = cloud_from_xyz(record, xyz_bytes)
        if self.source_frame != record['source_frame']:
            self._stop_current_node()
            self._start_for_source_frame(record['source_frame'])
        expected_stamp = str(record['header_timestamp_ns'])
        deadline = time.monotonic() + timeout_seconds
        started = time.monotonic()
        while time.monotonic() < deadline:
            self.publisher.publish(cloud)
            rclpy.spin_once(self.node, timeout_sec=0.1)
            matches = [item for item in self.received if item.get('header_timestamp_ns') == expected_stamp]
            if matches:
                result = matches[-1]
                if result.get('source_frame') != record['source_frame']:
                    raise ValueError('CPU result source frame does not match raw frame')
                if result.get('safety_decision_permitted') is not False:
                    raise ValueError('CPU catalog result must remain candidate-only')
                if result.get('noise_filter_mode') != self.noise_filter_mode:
                    raise ValueError('CPU ROS2 noise filter mode does not match request')
                if result.get('runtime_transport') != self.runtime_transport:
                    raise ValueError('CPU catalog requires ROS2 node output')
                if result.get('rail_selection_method') != self.rail_selection_method:
                    raise ValueError('CPU catalog result rail selection method does not match request')
                if result.get('rail_search_config') != self.rail_search_config:
                    raise ValueError('CPU catalog result rail search config does not match request')
                if result.get('forward_extension_method') != self.forward_extension_config['method']:
                    raise ValueError('CPU catalog result forward extension method does not match request')
                if result.get('arc_extension_horizon_m') != self.forward_extension_config['arc_horizon_m']:
                    raise ValueError('CPU catalog result arc extension horizon does not match request')
                if result.get('min_arc_radius_m') != self.forward_extension_config['min_arc_radius_m']:
                    raise ValueError('CPU catalog result min arc radius does not match request')
                if result.get('max_arc_turn_deg') != self.forward_extension_config['max_arc_turn_deg']:
                    raise ValueError('CPU catalog result max arc turn does not match request')
                if result.get('arc_fit_window_pairs') != self.forward_extension_config['arc_fit_window_pairs']:
                    raise ValueError('CPU catalog result arc fit window does not match request')
                result['wall_processing_ms'] = (time.monotonic() - started) * 1000.0
                self.received.clear()
                return result
        raise TimeoutError('no matching CPU result before timeout')

    def close(self):
        self._stop_current_node()
        rclpy.shutdown()


class DirectDetailedCpuRuntime:
    """Streams viewer XYZF frames directly through C++ without ROS2 pub/sub."""

    def __init__(self, rail_selection_method='development_candidate', *, rail_forward_min_m=3.0,
                 rail_forward_max_m=80.0, rail_station_length_m=2.0, rail_cell_width_m=0.04,
                 forward_extension_method='tangent', arc_extension_horizon_m=0.0,
                 min_arc_radius_m=60.0, max_arc_turn_deg=8.0, arc_fit_window_pairs=5,
                 noise_filter_mode='baseline_v3', profile_model_filter=False):
        if rail_selection_method != 'development_candidate':
            raise ValueError('direct stream supports development_candidate only')
        if rail_forward_max_m != 80.0 or rail_station_length_m != 2.0 or rail_cell_width_m != 0.04:
            raise ValueError('direct stream supports the default rail range shape only')
        if forward_extension_method not in {'tangent', 'arc_limited', 'arc_clamped'}:
            raise ValueError('unsupported forward extension method')
        arc_values = (arc_extension_horizon_m, min_arc_radius_m, max_arc_turn_deg)
        if (not all(isinstance(value, (int, float)) and math.isfinite(value) for value in arc_values) or
                arc_extension_horizon_m < 0 or min_arc_radius_m <= 0 or max_arc_turn_deg <= 0):
            raise ValueError('arc extension parameters must be finite and nonnegative/positive')
        if not isinstance(arc_fit_window_pairs, int) or arc_fit_window_pairs < 3:
            raise ValueError('arc fit window must be an integer >= 3')
        if noise_filter_mode not in {'legacy', 'baseline_v3_assist_score', 'baseline_v3'}:
            raise ValueError('unsupported noise filter mode')
        self.rail_selection_method = rail_selection_method
        self.rail_search_config = {
            'forward_min_m': float(rail_forward_min_m),
            'forward_max_m': float(rail_forward_max_m),
            'station_length_m': float(rail_station_length_m),
            'cell_width_m': float(rail_cell_width_m),
        }
        self.forward_extension_config = {
            'method': forward_extension_method,
            'arc_horizon_m': float(arc_extension_horizon_m),
            'min_arc_radius_m': float(min_arc_radius_m),
            'max_arc_turn_deg': float(max_arc_turn_deg),
            'arc_fit_window_pairs': int(arc_fit_window_pairs),
        }
        self.noise_filter_mode = noise_filter_mode
        self.runtime_transport = 'direct_cpp'
        # Resolve the installed executable without launching ros2 or a DDS node.
        from ament_index_python.packages import get_package_prefix
        executable = Path(get_package_prefix('lidar_mosmetro3d_cpp')) / 'lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli'
        command = [str(executable), str(float(rail_forward_min_m))]
        if forward_extension_method == 'arc_limited':
            command.extend(['--arc-limited', str(float(arc_extension_horizon_m))])
        elif forward_extension_method == 'arc_clamped':
            command.extend(['--arc-clamped', str(float(arc_extension_horizon_m)),
                            str(float(min_arc_radius_m)), str(float(max_arc_turn_deg))])
            command.extend(['--arc-fit-window', str(int(arc_fit_window_pairs))])
        if noise_filter_mode == 'baseline_v3_assist_score':
            command.append('--use-model-filter')
        elif noise_filter_mode == 'baseline_v3':
            command.append('--use-baseline-v3-filter')
        if profile_model_filter:
            command.append('--profile-model-filter')
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def analyze(self, record, xyz_bytes, timeout_seconds=30.0):
        del timeout_seconds
        if self.process.poll() is not None:
            stderr = self.process.stderr.read().decode(errors='replace')
            raise RuntimeError(f'direct C++ stream is not running: {stderr[-2000:]}')
        started = time.monotonic()
        self.process.stdin.write(struct.pack('<Q', len(xyz_bytes) // 12))
        self.process.stdin.write(xyz_bytes)
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read().decode(errors='replace')
            raise RuntimeError(f'direct C++ stream ended unexpectedly: {stderr[-2000:]}')
        result = json.loads(line)
        if result.get('safety_decision_permitted') is not False:
            raise ValueError('direct C++ result must remain candidate-only')
        if result.get('rail_selection_method') != self.rail_selection_method:
            raise ValueError('direct C++ result rail selection method does not match request')
        if result.get('rail_search_config') != self.rail_search_config:
            raise ValueError('direct C++ rail search config does not match request')
        if result.get('forward_extension_method') != self.forward_extension_config['method']:
            raise ValueError('direct C++ forward extension method does not match request')
        if result.get('arc_extension_horizon_m') != self.forward_extension_config['arc_horizon_m']:
            raise ValueError('direct C++ arc extension horizon does not match request')
        if result.get('min_arc_radius_m') != self.forward_extension_config['min_arc_radius_m']:
            raise ValueError('direct C++ min arc radius does not match request')
        if result.get('max_arc_turn_deg') != self.forward_extension_config['max_arc_turn_deg']:
            raise ValueError('direct C++ max arc turn does not match request')
        if result.get('arc_fit_window_pairs') != self.forward_extension_config['arc_fit_window_pairs']:
            raise ValueError('direct C++ arc fit window does not match request')
        if result.get('noise_filter_mode', 'legacy') != self.noise_filter_mode:
            raise ValueError('direct C++ noise filter mode does not match request')
        result['header_timestamp_ns'] = str(record['header_timestamp_ns'])
        result['source_frame'] = record['source_frame']
        result['runtime_transport'] = self.runtime_transport
        result['wall_processing_ms'] = (time.monotonic() - started) * 1000.0
        return result

    def close(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
