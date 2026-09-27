"""Measure source-origin ranges in representative ROS 2 PointCloud2 frames.

This is deliberately not odometry.  It reports Euclidean ranges of valid,
non-zero LiDAR returns in their source frame and retains the sampled indices.
"""
import argparse
import json
import math
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

import numpy as np
import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud


def part_key(part):
    """Use numeric suffix where present; otherwise preserve metadata order."""
    name = part['path'].rsplit('_', 1)[-1].split('.', 1)[0]
    return int(name) if name.isdigit() else part['path']


def sample_indices(count):
    if count < 1:
        raise ValueError('Source has no messages')
    return sorted({0, count // 2, count - 1})


def source_specs(archive):
    with tarfile.open(archive, 'r:') as tar:
        members = {member.name.lstrip('./'): member for member in tar if member.isfile()}
        metadata_names = sorted(name for name in members if name.endswith('/metadata.yaml'))
        specs = []
        for metadata_name in metadata_names:
            metadata = yaml.safe_load(tar.extractfile(members[metadata_name]))['rosbag2_bagfile_information']
            prefix = metadata_name.rsplit('/', 1)[0]
            specs.append(dict(id=prefix, metadata=metadata, prefix=prefix,
                              member_names=set(members)))
    return specs


def record_for_index(connection, offset):
    row = connection.execute(
        'SELECT m.data,t.name,t.type,t.serialization_format '
        'FROM messages m JOIN topics t ON t.id=m.topic_id '
        'ORDER BY m.timestamp,m.id LIMIT 1 OFFSET ?', (offset,)).fetchone()
    if row is None:
        raise ValueError(f'Missing message at offset {offset}')
    data, topic, message_type, serialization = row
    if message_type != 'sensor_msgs/msg/PointCloud2' or serialization != 'cdr':
        raise ValueError(f'Unexpected contract: {topic}, {message_type}, {serialization}')
    return topic, deserialize_message(data, PointCloud2)


def measure_source(archive_path, spec):
    info = spec['metadata']
    parts = sorted(info['files'], key=part_key)
    expected = info['message_count']
    part_count_sum = sum(part['message_count'] for part in parts)
    if part_count_sum != expected:
        # The six single-file sources have known nested-count defects in their
        # metadata.  The root count was reconciled with SQLite in the audit.
        # Do not invent a distribution across multiple files.
        if len(parts) != 1:
            raise ValueError(f"{spec['id']}: multipart metadata message counts disagree")
        parts = [dict(parts[0], message_count=expected)]
    selected = sample_indices(expected)
    results = []
    with tempfile.TemporaryDirectory(prefix='source-range-') as temp:
        database = Path(temp) / 'part.db3'
        start = 0
        for part in parts:
            chosen = [index for index in selected if start <= index < start + part['message_count']]
            if not chosen:
                start += part['message_count']
                continue
            member_name = f"{spec['prefix']}/{part['path']}"
            if member_name not in spec['member_names']:
                raise ValueError(f'Missing archive member: {member_name}')
            with tarfile.open(archive_path, 'r:') as tar:
                member = next(member for member in tar.getmembers()
                              if member.name.lstrip('./') == member_name)
                with tar.extractfile(member) as source, database.open('wb') as target:
                    shutil.copyfileobj(source, target, 8 * 1024 * 1024)
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
            try:
                actual = connection.execute('SELECT count(*) FROM messages').fetchone()[0]
                if actual != part['message_count']:
                    raise ValueError(f"{member_name}: SQLite count {actual} != metadata {part['message_count']}")
                for index in chosen:
                    topic, message = record_for_index(connection, index - start)
                    stats, xyz = inspect_cloud(message)
                    radius = np.linalg.norm(xyz, axis=1)
                    results.append(dict(index=index, source_part=part['path'], topic=topic,
                                        frame=stats['frame'], nonzero_finite=stats['nonzero_finite'],
                                        range_source_units=dict(
                                            p50=float(np.quantile(radius, .50)),
                                            p95=float(np.quantile(radius, .95)),
                                            p99=float(np.quantile(radius, .99)),
                                            p999=float(np.quantile(radius, .999)),
                                            max=float(radius.max()))))
            finally:
                connection.close()
            start += part['message_count']
    results.sort(key=lambda row: row['index'])
    maxima = [row['range_source_units']['max'] for row in results]
    return dict(source=spec['id'], metadata_messages=expected, sampled_indices=selected,
                sampled_frame_count=len(results), frames=results,
                metadata_part_count_sum=part_count_sum,
                sampled_max_range_source_units=dict(min=float(min(maxima)), max=float(max(maxima))),
                interpretation='EUCLIDEAN_SOURCE_ORIGIN_RETURN_RANGE_NOT_TRAVEL_DISTANCE_OR_OBJECT_DETECTION_RANGE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f'Refusing to overwrite {args.output}')
    sources = []
    for archive in args.archive:
        for spec in source_specs(archive):
            print(json.dumps(dict(archive=str(archive), source=spec['id'], status='START')), flush=True)
            sources.append(measure_source(archive, spec))
    payload = dict(scope='THREE_REPRESENTATIVE_FRAMES_PER_SOURCE',
                   archives=[str(path) for path in args.archive], sources=sources,
                   units='SOURCE_UNITS_METRES_ASSUMED_NOT_EXTERNALLY_CALIBRATED',
                   exclusions='NONFINITE_AND_0_0_0_RETURNS_EXCLUDED',
                   path_distance='UNKNOWN_NO_ODOMETRY_SPEED_TF_OR_VALIDATED_REGISTRATION')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), sources=len(sources), status='OK'), ensure_ascii=False))


if __name__ == '__main__':
    main()
