"""Local dataset catalog and bounded, on-demand ROS2 archive reader."""
import argparse
from collections import OrderedDict
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tarfile
import tempfile
from urllib.parse import urlsplit

import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2
from cloud_input import inspect_cloud
from stage_2_player import encode_xyz_frame, frame_record


def experimental_new_data_overlay(config_path):
    """Publish only the existing ASSUMED frame-local visualization contract."""
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    frames = config.get('frames', {})
    profile = config.get('universal_fleet_envelope', {}).get('polygon_in_working_frame', {})
    directions = frames.get('axis_directions', {})
    if (config.get('contract', {}).get('status') != 'ASSUMED_HACKATHON' or
            config.get('activation', {}).get('safety_decision_permitted') is not False or
            config.get('activation', {}).get('clear_decision_permitted') is not False or
            frames.get('working_frame') != 'hesai_lidar' or
            frames.get('target_from_source') != 'hesai_lidar <- hesai_lidar' or
            directions != {'x': 'LATERAL_RIGHT_FACING_FORWARD_ASSUMED',
                           'y': 'LONGITUDINAL_FORWARD_IS_NEGATIVE_Y_ASSUMED',
                           'z': 'VERTICAL_UP_ASSUMED'} or
            profile.get('coordinate_system') != 'hesai_lidar'):
        raise ValueError('new_data experimental geometry contract is not safe to display')
    lateral, vertical = profile.get('lateral_extent_m'), profile.get('vertical_extent_m')
    if (not isinstance(lateral, list) or not isinstance(vertical, list) or len(lateral) != 2 or len(vertical) != 2 or
            not all(isinstance(value, (int, float)) for value in lateral + vertical) or
            lateral[0] >= lateral[1] or vertical[0] >= vertical[1]):
        raise ValueError('new_data experimental profile is invalid')
    return {
        'source_axis_assumption': {'longitudinal_axis': 'y', 'longitudinal_sign': -1,
                                   'lateral_axis': 'x', 'vertical_axis': 'z', 'source_units': 'm'},
        'reference_cross_section': {'lateral_extent_m': {'min': lateral[0], 'max': lateral[1]},
                                    'vertical_extent_above_rail_m': {'min': vertical[0], 'max': vertical[1]}},
    }


class ArchiveFrames:
    def __init__(self, path, visualization_overlay):
        self.path = path
        self.visualization_overlay = visualization_overlay
        self.cache = OrderedDict()
        self.temp = tempfile.TemporaryDirectory(prefix='lidar-player-')
        self.loaded = None
        with tarfile.open(path, 'r:') as archive:
            self.members = {m.name.lstrip('./'): m for m in archive if m.isfile()}
            member = self.members['new_data/metadata.yaml']
            self.meta = yaml.safe_load(archive.extractfile(member))['rosbag2_bagfile_information']
        topics = self.meta['topics_with_message_count']
        if any(t['topic_metadata']['type'] != 'sensor_msgs/msg/PointCloud2' or
               t['topic_metadata']['serialization_format'] != 'cdr' for t in topics):
            raise ValueError('Archive requires PointCloud2/cdr-only metadata')
        self.first_ns = self.meta['starting_time']['nanoseconds_since_epoch']
        self.lookup = []
        self.part_counts = {}
        for part in self.meta['files']:
            name = 'new_data/' + part['path']
            if name not in self.members:
                raise ValueError('Missing archive member: ' + name)
            self.part_counts[name] = part['message_count']
            for offset in range(part['message_count']):
                self.lookup.append((name, offset))
        if len(self.lookup) != self.meta['message_count']:
            raise ValueError('Metadata count mismatch')

    def manifest(self):
        return dict(format='lidar-mosmetro3d.xyzf', format_version=1, dataset='new_data',
                    frame_count=len(self.lookup), safety_decision_permitted=False,
                    geometry_enabled=True, geometry_status='EXPERIMENTAL_ASSUMED_FRAME_LOCAL_CANDIDATES_ONLY',
                    geometry_notice='Экспериментальная геометрия new_data: ось, габарит и расстояния ASSUMED; '
                                    'плеер показывает геометрические кандидаты без классификации. Без опоры рельсов геометрия кадра недоступна.',
                    object_candidates_enabled=False,
                    visualization_overlay=self.visualization_overlay,
                    playback_timing='NOMINAL_10_HZ_PLUS_IO_FOR_LAZY_ARCHIVE',
                    point_encoding=dict(decimation='NONE', bytes_per_point=12),
                    frames=[dict(index=i, metadata_url=f'/api/new_data/{i}.json') for i in range(len(self.lookup))])

    def frame(self, index):
        if not 0 <= index < len(self.lookup):
            raise IndexError('Frame outside dataset')
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        member_name, offset = self.lookup[index]
        database = Path(self.temp.name) / 'chunk.db3'
        if self.loaded != member_name:
            self.loaded = None
            with tarfile.open(self.path, 'r:') as archive:
                with archive.extractfile(self.members[member_name]) as source, database.open('wb') as target:
                    shutil.copyfileobj(source, target, 8 * 1024 * 1024)
            self.loaded = member_name
        connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        try:
            actual_count = connection.execute('SELECT count(*) FROM messages').fetchone()[0]
            if actual_count != self.part_counts[member_name]:
                raise ValueError('SQLite count disagrees with metadata; frame indexing cannot be trusted')
            row = connection.execute('SELECT m.timestamp,m.data,t.name,t.type,t.serialization_format '
                                     'FROM messages m JOIN topics t ON t.id=m.topic_id '
                                     'ORDER BY m.timestamp,m.id LIMIT 1 OFFSET ?', (offset,)).fetchone()
            if row is None or row[3:] != ('sensor_msgs/msg/PointCloud2', 'cdr'):
                raise ValueError('Invalid or missing PointCloud2 row')
            stamp, data, topic, _, _ = row
            stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
            record = frame_record(index, stamp, stats, xyz, self.first_ns, f'/api/new_data/{index}.xyzf')
            record.update(dataset_id='new_data', source_part=member_name, source_topic=topic)
            value = record, encode_xyz_frame(xyz)
        finally:
            connection.close()
        self.cache[index] = value
        while len(self.cache) > 3:
            self.cache.popitem(last=False)
        return value

    def close(self):
        self.temp.cleanup()


def serve(root, port):
    prepared = {p.parent.name.removeprefix('player_'): p.parent
                for p in (root / 'artefacts/stage_2').glob('player_*/manifest.json')}
    overlay = experimental_new_data_overlay(root / 'config/geometry_new_data_experiment.yaml')
    archive = ArchiveFrames(root / 'dataset/for_hackathon/new_data', overlay)
    catalog = [dict(id=k, label=k, manifest=f'/datasets/{k}/manifest.json') for k in sorted(prepared)]
    catalog.append(dict(id='new_data', label='new_data · 20 минут · по запросу', manifest='/api/new_data/manifest.json'))
    vendor = prepared.get('doubleT_obstacle')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/datasets.json':
                    return self.send_json(catalog)
                if path == '/api/new_data/manifest.json':
                    return self.send_json(archive.manifest())
                match = re.fullmatch(r'/api/new_data/(\d+)\.(json|xyzf)', path)
                if match:
                    record, data = archive.frame(int(match[1]))
                    return self.send_json(record) if match[2] == 'json' else self.send_bytes(data)
                match = re.fullmatch(r'/datasets/([A-Za-z0-9_-]+)/(manifest.json|frames/frame_\d+\.xyzf)', path)
                if match and match[1] in prepared:
                    file = prepared[match[1]] / match[2]
                    if match[2] == 'manifest.json':
                        manifest = json.loads(file.read_text(encoding='utf-8'))
                        manifest['dataset'] = match[1]
                        for frame in manifest['frames']:
                            if not re.fullmatch(r'frames/frame_\d+\.xyzf', frame['file']):
                                raise ValueError('Invalid prepared frame path')
                            frame['file'] = f'/datasets/{match[1]}/' + frame['file']
                        if match[1] != 'doubleT_obstacle':
                            manifest['geometry_enabled'] = False
                        return self.send_json(manifest)
                    return self.send_bytes(file.read_bytes())
                if path in ('/', '/index.html'):
                    return self.send_bytes((root/'web/stage_2_raw_player.html').read_bytes(), 'text/html; charset=utf-8')
                if re.fullmatch(r'/stage_[23]_[a-z0-9_]+\.(js|json)', path):
                    return self.send_bytes((root/'web'/path[1:]).read_bytes(), 'application/json' if path.endswith('.json') else 'text/javascript')
                if path in ('/vendor/three.min.js', '/vendor/OrbitControls.js') and vendor:
                    return self.send_bytes((vendor/path[1:]).read_bytes(), 'text/javascript')
                self.send_error(404)
            except (IndexError, FileNotFoundError):
                self.send_error(404)
            except Exception as exc:
                print(type(exc).__name__, str(exc), flush=True)
                self.send_error(500, 'Dataset decoding failed; no frame committed')

        def send_json(self, value):
            self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), 'application/json')

        def send_bytes(self, data, mime='application/octet-stream'):
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    try:
        HTTPServer(('0.0.0.0', port), Handler).serve_forever()
    finally:
        archive.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/workspace'))
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    serve(args.root, args.port)
