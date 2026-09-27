"""Offline diagnostic LiDAR motion estimate for new_data.

This uses only bag time and relative ICP of source-frame point clouds.  It is
not a calibrated odometry, pose graph, TF source, deskew input, or safety
signal.  It explicitly saves residual and correspondence diagnostics.
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

from analyze_new_data_motion import frame_sample, percentile, rigid_icp
from cloud_input import inspect_cloud


def part_key(item):
    return int(item['path'].rsplit('_', 1)[-1].split('.', 1)[0])


def selected_indices(count, strides):
    indices = {0, count - 1}
    for stride in strides:
        indices.update(range(0, count, stride))
        indices.add(count - 1)
    return sorted(indices)


def summarize_stride(samples, stride):
    anchors = sorted(set(range(0, max(samples) + 1, stride)) | {max(samples)})
    rows = []
    for previous_index, current_index in zip(anchors, anchors[1:]):
        previous, current = samples[previous_index], samples[current_index]
        interval_seconds = (current['bag_timestamp_ns'] - previous['bag_timestamp_ns']) / 1e9
        if interval_seconds <= 0:
            raise ValueError(f'Non-positive bag-time interval {previous_index}..{current_index}')
        result = rigid_icp(previous['sample'], current['sample'])
        row = dict(start_index=previous_index, end_index=current_index,
                   interval_seconds=interval_seconds,
                   start_bag_timestamp_ns=previous['bag_timestamp_ns'],
                   end_bag_timestamp_ns=current['bag_timestamp_ns'],
                   **(result or dict(translation_m=None, rotation_deg=None,
                                     residual_median_m=None, correspondence_fraction=None)))
        if row['translation_m'] is not None:
            row['speed_m_s'] = row['translation_m'] / interval_seconds
            row['speed_km_h'] = row['speed_m_s'] * 3.6
        else:
            row['speed_m_s'] = None
            row['speed_km_h'] = None
        rows.append(row)
    usable = [row for row in rows if row['translation_m'] is not None]
    total_seconds = sum(row['interval_seconds'] for row in rows)
    covered_seconds = sum(row['interval_seconds'] for row in usable)
    path_m = sum(row['translation_m'] for row in usable)
    values = lambda name: [row[name] for row in usable]
    return dict(anchor_stride_frames=stride, interval_count=len(rows),
                registration_count=len(usable),
                covered_time_fraction=covered_seconds / total_seconds if total_seconds else None,
                bag_duration_seconds=total_seconds,
                lidar_icp_path_sum_m=path_m,
                lidar_icp_mean_speed_m_s=path_m / covered_seconds if covered_seconds else None,
                lidar_icp_mean_speed_km_h=(path_m / covered_seconds * 3.6) if covered_seconds else None,
                interval_speed_m_s={str(q): percentile(values('speed_m_s'), q) for q in (.05, .5, .95)},
                interval_speed_km_h={str(q): percentile(values('speed_km_h'), q) for q in (.05, .5, .95)},
                residual_median_m={str(q): percentile(values('residual_median_m'), q) for q in (.05, .5, .95)},
                correspondence_fraction={str(q): percentile(values('correspondence_fraction'), q) for q in (.05, .5, .95)},
                intervals=rows,
                interpretation='DIAGNOSTIC_RELATIVE_ICP_NOT_CALIBRATED_ODOMETRY')


def run(archive_path, output, strides):
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    with tarfile.open(archive_path, 'r:') as archive:
        members = {member.name.lstrip('./'): member for member in archive if member.isfile()}
        info = yaml.safe_load(archive.extractfile(members['new_data/metadata.yaml']))['rosbag2_bagfile_information']
    parts = sorted(info['files'], key=part_key)
    count = info['message_count']
    if sum(part['message_count'] for part in parts) != count:
        raise ValueError('new_data metadata message counts disagree')
    wanted = selected_indices(count, strides)
    config = dict(voxel_m=0.2, min_range_m=4.0, max_range_m=35.0, max_sample_points=6000,
                  icp_iterations=12, icp_max_distance_m=0.7)
    samples, start = {}, 0
    with tempfile.TemporaryDirectory(prefix='new-data-lidar-motion-') as temp:
        database = Path(temp) / 'part.db3'
        for part_number, part in enumerate(parts):
            current = [index for index in wanted if start <= index < start + part['message_count']]
            if current:
                member_name = 'new_data/' + part['path']
                with tarfile.open(archive_path, 'r:') as archive:
                    member = next(item for item in archive.getmembers()
                                  if item.name.lstrip('./') == member_name)
                    with archive.extractfile(member) as source, database.open('wb') as target:
                        shutil.copyfileobj(source, target, 8 * 1024 * 1024)
                connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
                try:
                    actual = connection.execute('SELECT count(*) FROM messages').fetchone()[0]
                    if actual != part['message_count']:
                        raise ValueError(f"{part['path']}: SQLite count {actual} != metadata")
                    for index in current:
                        row = connection.execute(
                            'SELECT m.timestamp,m.data,t.name,t.type,t.serialization_format '
                            'FROM messages m JOIN topics t ON t.id=m.topic_id '
                            'ORDER BY m.timestamp,m.id LIMIT 1 OFFSET ?', (index - start,)).fetchone()
                        if row is None or row[2:] != ('/lidar_points', 'sensor_msgs/msg/PointCloud2', 'cdr'):
                            raise ValueError(f'Unexpected message contract at {index}')
                        stats, xyz = inspect_cloud(deserialize_message(row[1], PointCloud2))
                        if stats['frame'] != 'hesai_lidar':
                            raise ValueError(f'Unexpected frame at {index}: {stats["frame"]}')
                        sample, _ = frame_sample(xyz, config['voxel_m'], config['min_range_m'],
                                                 config['max_range_m'], config['max_sample_points'])
                        samples[index] = dict(bag_timestamp_ns=row[0], sample=sample,
                                              usable_points=stats['nonzero_finite'], sample_points=len(sample))
                finally:
                    connection.close()
            start += part['message_count']
            print(json.dumps(dict(part=part_number + 1, parts=len(parts), anchors_read=len(samples))), flush=True)
    if sorted(samples) != wanted:
        raise ValueError(f'Read {len(samples)} anchors; expected {len(wanted)}')
    summaries = [summarize_stride(samples, stride) for stride in strides]
    payload = dict(scope='OFFLINE_DIAGNOSTIC_RELATIVE_ICP', source_archive=str(archive_path),
                   metadata_message_count=count, bag_duration_seconds=info['duration']['nanoseconds'] / 1e9,
                   sampled_anchor_count=len(samples), anchor_indices=wanted, source_frame='hesai_lidar',
                   source_topic='/lidar_points', config=config, anchor_summaries=summaries,
                   limitations=['NO_ODOMETRY_IMU_TF_OR_EXTERNAL_TRAJECTORY',
                                'SOURCE_UNITS_M_ASSUMED_NOT_EXTERNALLY_CALIBRATED',
                                'ICP_PATH_SUM_CAN_DRIFT_OR_UNDER_OR_OVERESTIMATE_CURVED_TRAJECTORY',
                                'NOT_FOR_DESKEW_ACCUMULATION_TTC_OR_SAFETY_DECISION'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(output), status='OK', anchors=len(samples)), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('dataset/for_hackathon/new_data'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--anchor-strides', type=int, nargs='+', default=[10, 50])
    args = parser.parse_args()
    if any(stride < 1 for stride in args.anchor_strides):
        raise ValueError('anchor stride must be positive')
    run(args.archive, args.output, sorted(set(args.anchor_strides)))
