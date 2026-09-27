"""Probe sleeper-period phase shifts in a bounded initial new_data window.

The output is a diagnostic periodic signal, not train odometry.  In particular,
cross-correlation peaks separated by a sleeper pitch are an unavoidable
ambiguity when the train moves by one or more pitches per frame.
"""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

import numpy as np
import yaml
from scipy.signal import correlate, find_peaks
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud


def extract_window(archive_path, start, count):
    with tarfile.open(archive_path, 'r:') as archive:
        members = {member.name.lstrip('./'): member for member in archive if member.isfile()}
        info = yaml.safe_load(archive.extractfile(members['new_data/metadata.yaml']))['rosbag2_bagfile_information']
    if start < 0 or count < 2 or start + count > info['message_count']:
        raise ValueError('Requested window outside new_data')
    parts = sorted(info['files'], key=lambda item: int(item['path'].rsplit('_', 1)[-1].split('.')[0]))
    wanted = range(start, start + count)
    rows, offset = [], 0
    with tempfile.TemporaryDirectory(prefix='sleeper-phase-') as temp:
        database = Path(temp) / 'part.db3'
        for part in parts:
            selected = [index for index in wanted if offset <= index < offset + part['message_count']]
            if selected:
                name = 'new_data/' + part['path']
                with tarfile.open(archive_path, 'r:') as archive:
                    member = next(item for item in archive.getmembers() if item.name.lstrip('./') == name)
                    with archive.extractfile(member) as source, database.open('wb') as target:
                        shutil.copyfileobj(source, target, 8 * 1024 * 1024)
                connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
                try:
                    actual = connection.execute('SELECT count(*) FROM messages').fetchone()[0]
                    if actual != part['message_count']:
                        raise ValueError(f"{part['path']}: SQLite count mismatch")
                    for index in selected:
                        row = connection.execute(
                            'SELECT m.timestamp,m.data,t.name,t.type,t.serialization_format '
                            'FROM messages m JOIN topics t ON t.id=m.topic_id '
                            'ORDER BY m.timestamp,m.id LIMIT 1 OFFSET ?', (index - offset,)).fetchone()
                        if row is None or row[2:] != ('/lidar_points', 'sensor_msgs/msg/PointCloud2', 'cdr'):
                            raise ValueError(f'Unexpected PointCloud2 contract at {index}')
                        stats, xyz = inspect_cloud(deserialize_message(row[1], PointCloud2))
                        if stats['frame'] != 'hesai_lidar':
                            raise ValueError(f'Unexpected frame at {index}: {stats["frame"]}')
                        rows.append((index, row[0], xyz))
                finally:
                    connection.close()
            offset += part['message_count']
    if len(rows) != count:
        raise ValueError(f'Read {len(rows)} instead of {count} frames')
    return rows


def sleeper_signal(xyz, edges, x_min, x_max, z_min, z_max, occupancy_x_bin_m):
    # Raw source coordinates only: centre band around observed rail/sleeper deck.
    s = -xyz[:, 1]
    mask = ((s >= edges[0]) & (s < edges[-1]) & (xyz[:, 0] >= x_min) & (xyz[:, 0] <= x_max) &
            (xyz[:, 2] >= z_min) & (xyz[:, 2] <= z_max))
    # Count occupied lateral cells rather than raw returns: a sleeper should
    # span the track width, whereas ray-density stripes need not do so.
    lateral_edges = np.arange(x_min, x_max + occupancy_x_bin_m, occupancy_x_bin_m)
    cells, _, _ = np.histogram2d(s[mask], xyz[:, 0][mask], bins=(edges, lateral_edges))
    signal = np.count_nonzero(cells, axis=1)
    # Avoid individual ring-stripe spikes without erasing a ~0.5 m periodicity.
    return np.convolve(signal.astype(float), np.ones(3) / 3, mode='same'), int(mask.sum())


def normalized_correlation(previous, current, bin_m, max_shift_m, pitch_m):
    previous = previous - previous.mean()
    current = current - current.mean()
    raw = correlate(current, previous, mode='full')
    lags = np.arange(-len(previous) + 1, len(previous))
    keep = np.abs(lags * bin_m) <= max_shift_m
    values, lags = raw[keep], lags[keep]
    denom = np.linalg.norm(previous) * np.linalg.norm(current)
    values = values / denom if denom else values
    peaks, _ = find_peaks(values, distance=max(1, round(pitch_m / bin_m * .65)))
    order = peaks[np.argsort(values[peaks])[::-1]][:8]
    top = [dict(shift_m=float(lags[index] * bin_m), correlation=float(values[index])) for index in order]
    return top


def run(args):
    if args.output.exists():
        raise FileExistsError(f'Refusing to overwrite {args.output}')
    rows = extract_window(args.archive, args.start, args.count)
    edges = np.arange(args.range_min_m, args.range_max_m + args.bin_m, args.bin_m)
    signals, usable = [], []
    for index, timestamp, xyz in rows:
        signal, point_count = sleeper_signal(xyz, edges, args.x_min, args.x_max, args.z_min, args.z_max,
                                              args.occupancy_x_bin_m)
        signals.append(signal)
        usable.append(point_count)
    reference = signals[0] - signals[0].mean()
    autocorrelation = correlate(reference, reference, mode='full')[len(reference) - 1:]
    lower, upper = round(.40 / args.bin_m), round(.70 / args.bin_m)
    period_lag = lower + int(np.argmax(autocorrelation[lower:upper]))
    frame_rows = []
    for ordinal, ((index, timestamp, _), signal) in enumerate(zip(rows, signals)):
        prior = signals[ordinal - 1] if ordinal else None
        peaks = normalized_correlation(prior, signal, args.bin_m, args.max_shift_m, args.pitch_m) if prior is not None else []
        frame_rows.append(dict(index=index, bag_timestamp_ns=timestamp, sleeper_band_points=usable[ordinal],
                               previous_phase_candidates=peaks))
    payload = dict(scope='INITIAL_WINDOW_SLEEVER_PHASE_PROBE_NOT_ODOMETRY',
                   frame_interval=[args.start, args.start + args.count - 1], frame_count=args.count,
                   source_frame='hesai_lidar', time_base='BAG_TIMESTAMPS_ONLY',
                   source_axis_hypothesis='s=-Y', bin_m=args.bin_m,
                   sleeper_band=dict(x_m=[args.x_min, args.x_max], z_m=[args.z_min, args.z_max],
                                     s_m=[args.range_min_m, args.range_max_m],
                                     occupancy_x_bin_m=args.occupancy_x_bin_m),
                   assumed_sleeper_pitch_m=args.pitch_m,
                   observed_reference_autocorrelation_period_m=float(period_lag * args.bin_m),
                   phase_alias_speed_increment_km_h=float(args.pitch_m / ((rows[-1][1] - rows[0][1]) / (args.count - 1) / 1e9) * 3.6),
                   frames=frame_rows,
                   limitations=['PITCH_IS_A_HYPOTHESIS_NOT_CONFIRMED_TRACK_METADATA',
                                'PHASE_SHIFT_IS_PERIODIC_AND_AMBIGUOUS_BY_INTEGER_SLEEPER_PITCHES',
                                'NO_SPEED_OR_DISTANCE_OUTPUT_IS_PERMITTED_WITHOUT_UNWRAPPING_EVIDENCE'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), observed_period_m=payload['observed_reference_autocorrelation_period_m'], status='OK')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('dataset/for_hackathon/new_data'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--count', type=int, default=101)
    parser.add_argument('--pitch-m', type=float, default=1000 / 1840)
    parser.add_argument('--bin-m', type=float, default=.01)
    parser.add_argument('--range-min-m', type=float, default=4.0)
    parser.add_argument('--range-max-m', type=float, default=30.0)
    parser.add_argument('--x-min', type=float, default=-2.5)
    parser.add_argument('--x-max', type=float, default=2.5)
    parser.add_argument('--z-min', type=float, default=-1.65)
    parser.add_argument('--z-max', type=float, default=-1.05)
    parser.add_argument('--occupancy-x-bin-m', type=float, default=.05)
    parser.add_argument('--max-shift-m', type=float, default=3.0)
    run(parser.parse_args())
