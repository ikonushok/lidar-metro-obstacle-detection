"""Bounded offline development experiment; original PointCloud2 and XYZ preserved."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud
from stage_3_baseline import evaluate_cloud, load_geometry_contract


def window_messages(path, indices):
    """Decode selected original messages, verifying part count and topic contract."""
    with tarfile.open(path, 'r:') as archive:
        members = {m.name.lstrip('./'): m for m in archive if m.isfile()}
        meta = yaml.safe_load(archive.extractfile(members['new_data/metadata.yaml']))['rosbag2_bagfile_information']
    parts = sorted(meta['files'], key=lambda p: int(p['path'].rsplit('_', 1)[-1].split('.')[0]))
    if sum(p['message_count'] for p in parts) != meta['message_count']:
        raise ValueError('Metadata count mismatch')
    if not indices or min(indices) < 0 or max(indices) >= meta['message_count']:
        raise ValueError('Requested window outside archive')
    first_ns = meta['starting_time']['nanoseconds_since_epoch']
    with tempfile.TemporaryDirectory(prefix='new-data-baseline-') as temporary:
        database = Path(temporary) / 'part.db3'
        begin = 0
        for part in parts:
            selected = sorted(i for i in indices if begin <= i < begin + part['message_count'])
            if selected:
                name = 'new_data/' + part['path']
                with tarfile.open(path, 'r:') as archive:
                    with archive.extractfile(members[name]) as source, database.open('wb') as target:
                        shutil.copyfileobj(source, target, 8 * 1024 * 1024)
                connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
                try:
                    if connection.execute('SELECT count(*) FROM messages').fetchone()[0] != part['message_count']:
                        raise ValueError('SQLite count differs from metadata')
                    for index in selected:
                        row = connection.execute(
                            'SELECT m.timestamp,m.data,t.name,t.type,t.serialization_format '
                            'FROM messages m JOIN topics t ON t.id=m.topic_id '
                            'ORDER BY m.timestamp,m.id LIMIT 1 OFFSET ?', (index - begin,)).fetchone()
                        if row is None or row[2:] != ('/lidar_points', 'sensor_msgs/msg/PointCloud2', 'cdr'):
                            raise ValueError('Unexpected topic/type/serialization')
                        stamp, data = row[:2]
                        yield index, stamp, first_ns, part['path'], deserialize_message(data, PointCloud2)
                finally:
                    connection.close()
            begin += part['message_count']


def projection(xyz, index, output, result=None):
    """Raw density projections; fixed source axes, no inferred coordinate transform."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for ax, a, b, xlim, ylim in zip(axes, (0, 1, 0), (1, 2, 2),
                                   ((-10, 10), (-65, 15), (-7, 7)),
                                   ((-65, 15), (-7, 7), (-7, 7))):
        ax.hist2d(xyz[:, a], xyz[:, b], bins=(350, 350), range=(xlim, ylim),
                  norm=matplotlib.colors.LogNorm(), cmap='viridis')
        ax.set(xlabel='XYZ'[a] + ' (source units)', ylabel='XYZ'[b] + ' (source units)',
               xlim=xlim, ylim=ylim)
        ax.grid(alpha=.2)
        if result:
            for cluster in result.get('clusters', []):
                bounds = cluster['bounds_source_coordinates']
                x, y = bounds['xyz'[a]], bounds['xyz'[b]]
                ax.add_patch(matplotlib.patches.Rectangle((x['min'], y['min']),
                    x['max']-x['min'], y['max']-y['min'], fill=False, color='orangered', lw=.7))
    fig.suptitle(f'new_data / frame {index} / hesai_lidar / RAW XYZ' +
                 (' / candidate boxes, NOT verified obstacles' if result else ''))
    fig.savefig(output / f'frame_{index:05d}.png', dpi=130)
    plt.close(fig)


def run(args):
    indices = set(args.indices) if args.indices else set(range(args.start, args.start + args.count))
    args.output.mkdir(parents=True, exist_ok=True)
    config = load_geometry_contract(args.config) if args.config else None
    summaries, durations = [], []
    # A unique output folder is required: never overwrite an existing completed run.
    with (args.output / 'frames.jsonl').open('x', encoding='utf-8') as stream:
        if config:
            (args.output / 'profile_snapshot.yaml').write_bytes(args.config.read_bytes())
        for index, stamp, first_ns, part, msg in window_messages(args.archive, indices):
            stats, xyz = inspect_cloud(msg)
            if stats['frame'] != 'hesai_lidar':
                raise ValueError('Unexpected source frame; no frame renaming permitted')
            before = hashlib.sha256(msg.data).hexdigest()
            started = time.perf_counter()
            result = evaluate_cloud(msg, config) if config else None
            elapsed = (time.perf_counter() - started) * 1000 if config else None
            if hashlib.sha256(msg.data).hexdigest() != before:
                raise ValueError('Source buffer modified')
            if result and (result['safety_decision_permitted'] or result['clear_decision_permitted']):
                raise ValueError('Safety decision prohibited')
            row = dict(index=index, source_part=part, bag_timestamp_ns=str(stamp),
                       header_timestamp_ns=str(stats['header_ns']),
                       bag_offset_seconds=(stamp-first_ns)/1e9, input=stats,
                       source_sha256=before, processing_ms=elapsed, result=result)
            summaries.append(row)
            if elapsed is not None:
                durations.append(elapsed)
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            if args.export_xyz:
                np.asarray(xyz, dtype='<f4').tofile(args.output / f'frame_{index:05d}.xyzf')
            if args.indices or index in (min(indices), sorted(indices)[len(indices)//2], max(indices)):
                projection(xyz, index, args.output, result)
                np.save(args.output / f'frame_{index:05d}.npy', xyz)
                np.asarray(xyz, dtype='<f4').tofile(args.output / f'frame_{index:05d}.xyzf')
            print(json.dumps(dict(index=index, processing_ms=elapsed,
                                  status=result['status'] if result else 'RAW_INSPECTION')), flush=True)
    if len(summaries) != len(indices):
        raise ValueError('Window incomplete')
    summary = dict(dataset='new_data', scope='OFFLINE_DEVELOPMENT_WINDOW_NOT_TEST_OR_ODOMETRY',
                   frame_count=len(summaries), first_index=min(indices), last_index=max(indices),
                   bag_offset_range_seconds=[summaries[0]['bag_offset_seconds'], summaries[-1]['bag_offset_seconds']],
                   source_frame='hesai_lidar', source_mutations=0,
                   config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest() if args.config else None,
                   safety_decision_permitted=False, clear_decision_permitted=False,
                   status_counts=dict(Counter(r['result']['status'] for r in summaries if r['result'])),
                   processing_ms={str(q): float(np.quantile(durations, q)) for q in (.5, .95, 1)} if durations else None,
                   geometry_assumptions_validated=False, motion_compensation=False,
                   quality_metrics=None, quality_reason='NO_EVENT_OR_INFRASTRUCTURE_GROUND_TRUTH')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--count', type=int, default=101)
    parser.add_argument('--indices', type=int, nargs='+')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--export-xyz', action='store_true', help='Export full usable XYZ for separate visual replay')
    args = parser.parse_args()
    run(args)
