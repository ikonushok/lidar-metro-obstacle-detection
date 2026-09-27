"""Read every new_data cloud and produce conservative motion diagnostics.

This is not odometry: it measures repeatability of local tunnel geometry in
the LiDAR frame.  No result is used for deskew, accumulation or safety logic.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
import time

import numpy as np
import yaml
from scipy.spatial import cKDTree
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud


def percentile(values, q):
    finite = [value for value in values if math.isfinite(value)]
    return float(np.quantile(finite, q)) if finite else None


def frame_sample(xyz, voxel, min_range, max_range, max_points):
    """One source return per voxel; origin-centric and axis-independent."""
    radius = np.linalg.norm(xyz, axis=1)
    selected = xyz[(radius >= min_range) & (radius <= max_range)]
    if not len(selected):
        return selected, set()
    cells = np.floor(selected / voxel).astype(np.int32)
    _, first = np.unique(cells, axis=0, return_index=True)
    sample = selected[np.sort(first)]
    if len(sample) > max_points:
        sample = sample[::math.ceil(len(sample) / max_points)]
    return sample, {tuple(cell) for cell in cells}


def nearest_metrics(previous, current):
    if not len(previous) or not len(current):
        return None, None
    distance, _ = cKDTree(current).query(previous, workers=-1)
    return float(np.median(distance)), float(np.mean(distance <= 0.1))


def rigid_icp(source, target, iterations=12, max_distance=0.7):
    """Trimmed point-to-point registration used only at one-second anchors."""
    if len(source) < 100 or len(target) < 100:
        return None
    transformed = source.copy()
    rotation = np.eye(3)
    translation = np.zeros(3)
    tree = cKDTree(target)
    for _ in range(iterations):
        distance, nearest = tree.query(transformed, workers=-1)
        limit = min(max_distance, float(np.quantile(distance, 0.75)))
        keep = distance <= limit
        if keep.sum() < 100:
            return None
        a, b = transformed[keep], target[nearest[keep]]
        ac, bc = a.mean(axis=0), b.mean(axis=0)
        u, _, vt = np.linalg.svd((a - ac).T @ (b - bc))
        delta_rotation = vt.T @ u.T
        if np.linalg.det(delta_rotation) < 0:
            vt[-1] *= -1
            delta_rotation = vt.T @ u.T
        delta_translation = bc - delta_rotation @ ac
        transformed = transformed @ delta_rotation.T + delta_translation
        translation = delta_rotation @ translation + delta_translation
        rotation = delta_rotation @ rotation
    distance, _ = tree.query(transformed, workers=-1)
    angle = math.degrees(math.acos(float(np.clip((np.trace(rotation) - 1) / 2, -1, 1))))
    return dict(translation_m=float(np.linalg.norm(translation)), rotation_deg=angle,
                residual_median_m=float(np.median(distance)),
                correspondence_fraction=float(np.mean(distance <= 0.1)))


def member_sort_key(item):
    suffix = item['path'].rsplit('_', 1)[-1].split('.', 1)[0]
    return int(suffix)


def run(archive_path, output, max_parts=None):
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tarfile.open(archive_path, 'r:') as archive:
        members = {member.name.lstrip('./'): member for member in archive if member.isfile()}
        metadata = yaml.safe_load(archive.extractfile(members['new_data/metadata.yaml']))['rosbag2_bagfile_information']
    parts = sorted(metadata['files'], key=member_sort_key)
    if max_parts is not None:
        parts = parts[:max_parts]
    if any(part['message_count'] <= 0 for part in parts):
        raise ValueError('Metadata contains empty part')
    frame_count_expected = sum(part['message_count'] for part in parts)
    config = dict(voxel_m=0.2, min_range_m=4.0, max_range_m=35.0, max_sample_points=6000,
                  registration_stride_frames=50, icp_max_distance_m=0.7)
    rows, registration_rows = [], []
    previous_sample = previous_anchor = None
    previous_cells = None
    frame_index = 0
    source_frame = None
    with tempfile.TemporaryDirectory(prefix='new-data-motion-') as temp_dir:
        database = Path(temp_dir) / 'part.db3'
        for part_number, part in enumerate(parts):
            member_name = 'new_data/' + part['path']
            member = members.get(member_name)
            if member is None:
                raise ValueError('Missing archive part: ' + member_name)
            with tarfile.open(archive_path, 'r:') as archive:
                with archive.extractfile(member) as source, database.open('wb') as target:
                    shutil.copyfileobj(source, target, 8 * 1024 * 1024)
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
            try:
                actual = connection.execute('SELECT count(*) FROM messages').fetchone()[0]
                if actual != part['message_count']:
                    raise ValueError(f'{part["path"]}: SQLite count {actual} != metadata {part["message_count"]}')
                records = connection.execute(
                    'SELECT m.timestamp,m.data,t.name,t.type,t.serialization_format '
                    'FROM messages m JOIN topics t ON t.id=m.topic_id ORDER BY m.timestamp,m.id')
                for timestamp, data, topic, msg_type, serialization in records:
                    if topic != '/lidar_points' or msg_type != 'sensor_msgs/msg/PointCloud2' or serialization != 'cdr':
                        raise ValueError('Unexpected message contract')
                    stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
                    if source_frame is None:
                        source_frame = stats['frame']
                    elif source_frame != stats['frame']:
                        raise ValueError('source_frame changed within new_data')
                    sample, cells = frame_sample(xyz, config['voxel_m'], config['min_range_m'],
                                                  config['max_range_m'], config['max_sample_points'])
                    median, near = nearest_metrics(previous_sample, sample) if previous_sample is not None else (None, None)
                    if previous_cells is None:
                        overlap = None
                    else:
                        union = len(previous_cells | cells)
                        overlap = len(previous_cells & cells) / union if union else None
                    row = dict(index=frame_index, bag_timestamp_ns=timestamp,
                               header_timestamp_ns=stats['header_ns'], source_part=part['path'],
                               source_points=stats['points'], usable_points=stats['nonzero_finite'],
                               sample_points=len(sample), voxel_count=len(cells),
                               previous_nn_median_m=median, previous_nn_fraction_10cm=near,
                               previous_voxel_jaccard=overlap)
                    rows.append(row)
                    if frame_index % config['registration_stride_frames'] == 0:
                        if previous_anchor is not None:
                            registration = rigid_icp(previous_anchor['sample'], sample,
                                                     max_distance=config['icp_max_distance_m'])
                            registration_rows.append(dict(start_index=previous_anchor['index'], end_index=frame_index,
                                                          start_bag_timestamp_ns=previous_anchor['timestamp'],
                                                          end_bag_timestamp_ns=timestamp,
                                                          interval_seconds=(timestamp - previous_anchor['timestamp']) / 1e9,
                                                          **(registration or dict(translation_m=None, rotation_deg=None,
                                                                                 residual_median_m=None, correspondence_fraction=None))))
                        previous_anchor = dict(index=frame_index, timestamp=timestamp, sample=sample)
                    previous_sample, previous_cells = sample, cells
                    frame_index += 1
            finally:
                connection.close()
            print(json.dumps(dict(part=part_number + 1, parts=len(parts), frames=frame_index,
                                  elapsed_seconds=round(time.monotonic() - started, 1))), flush=True)
    if frame_index != frame_count_expected:
        raise ValueError(f'Read {frame_index} frames; expected {frame_count_expected}')
    for name, collection in (('frames.csv', rows), ('registration_1s.csv', registration_rows)):
        with (output / name).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=collection[0].keys() if collection else [])
            writer.writeheader()
            writer.writerows(collection)
    median_nn = [row['previous_nn_median_m'] for row in rows[1:]]
    overlap = [row['previous_voxel_jaccard'] for row in rows[1:]]
    translations = [row['translation_m'] for row in registration_rows]
    residuals = [row['residual_median_m'] for row in registration_rows]
    summary = dict(scope='ALL_FRAMES_IN_NEW_DATA' if max_parts is None else 'PREFIX_ONLY',
                   input_archive_bytes=archive_path.stat().st_size, parts_read=len(parts), frames_read=frame_index,
                   metadata_frame_count=metadata['message_count'], source_frame=source_frame,
                   source_topic='/lidar_points', config=config,
                   adjacent_frame=dict(nn_median_m={str(q): percentile(median_nn, q) for q in (.05, .5, .95)},
                                       voxel_jaccard={str(q): percentile(overlap, q) for q in (.05, .5, .95)}),
                   one_second_registration=dict(samples=len(registration_rows),
                                                translation_m={str(q): percentile(translations, q) for q in (.05, .5, .95)},
                                                residual_median_m={str(q): percentile(residuals, q) for q in (.05, .5, .95)}),
                   motion_conclusion='DIAGNOSTIC_ONLY_NOT_ODOMETRY_OR_TRAIN_STATE',
                   elapsed_seconds=time.monotonic() - started)
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('dataset/for_hackathon/new_data'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-parts', type=int)
    args = parser.parse_args()
    run(args.archive, args.output, args.max_parts)
