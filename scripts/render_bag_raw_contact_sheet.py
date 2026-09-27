"""Render a stratified, source-only bag review without invoking AutoRails.

This is an experimental inspection aid.  It deliberately makes no rail, route,
or switch decision and stores no detector-derived points.  Coordinate labels
remain in the source frame because this script does not calibrate them.
"""

import argparse
import json
from math import ceil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud


def selected_indices(count, stride):
    """Include both endpoints even when the stride does not divide count - 1."""
    indices = list(range(0, count, stride))
    if indices[-1] != count - 1:
        indices.append(count - 1)
    return indices


def plot_sheet(records, output, bag_name, columns):
    rows = ceil(len(records) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(3.1 * columns, 3.0 * rows),
                             squeeze=False)
    for ax in axes.flat:
        ax.set_visible(False)
    for (frame_index, stats, xyz), ax in zip(records, axes.flat):
        # Display-only subsampling; decoded source return selection is unchanged.
        shown = xyz[::max(1, len(xyz) // 12000)]
        ax.scatter(shown[:, 0], shown[:, 1], s=.18, alpha=.35, color='#1f77b4')
        ax.set_xlim(-5, 5)
        ax.set_ylim(-45, 2)
        ax.set_aspect('equal', adjustable='box')
        ax.grid(alpha=.2)
        ax.set_title('frame %d | %d nz finite' % (frame_index, stats['nonzero_finite']),
                     fontsize=8)
        ax.set_xlabel('X source', fontsize=7)
        ax.set_ylabel('Y source', fontsize=7)
        ax.tick_params(labelsize=6)
        ax.set_visible(True)
    fig.suptitle('%s | stratified raw source XY review\n'
                 'No AutoRails, no rail labels, source coordinates not calibrated' % bag_name,
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stride', type=int, default=25)
    parser.add_argument('--columns', type=int, default=6)
    args = parser.parse_args()
    if args.stride <= 0 or args.columns <= 0:
        parser.error('--stride and --columns must be positive')

    databases = list(args.bag.glob('*.db3'))
    if len(databases) != 1:
        parser.error('Expected exactly one .db3 in bag directory')
    import sqlite3
    connection = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    try:
        total = connection.execute('select count(*) from messages').fetchone()[0]
    finally:
        connection.close()
    indices = set(selected_indices(total, args.stride))
    # Fetch only selected bag-ordered rows.  This preserves the declared sample
    # indices while avoiding a hidden decode of every source cloud.
    records = []
    connection = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    try:
        topics = {row[0]: (row[2], row[3]) for row in connection.execute(
            'select id,name,type,serialization_format from topics')}
        for frame_index in sorted(indices):
            row = connection.execute(
                'select id,topic_id,timestamp,data from messages order by timestamp,id '
                'limit 1 offset ?', (frame_index,)).fetchone()
            if row is None:
                raise RuntimeError('Missing selected frame %d' % frame_index)
            _rowid, topic_id, _bag_ns, data = row
            message_type, serialization = topics[topic_id]
            if message_type != 'sensor_msgs/msg/PointCloud2' or serialization != 'cdr':
                raise ValueError('Unsupported topic at frame %d' % frame_index)
            stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
            records.append((frame_index, stats, xyz))
    finally:
        connection.close()

    if len(records) != len(indices):
        raise RuntimeError('Selected frame count mismatch: got %d, expected %d' %
                           (len(records), len(indices)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    plot_sheet(records, args.output, args.bag.name, args.columns)
    manifest = {
        'purpose': 'raw-only stratified visual review; not ground truth',
        'bag': str(args.bag),
        'database_messages': total,
        'selected_indices': sorted(indices),
        'selection_rule': 'every %dth bag-ordered message plus final message' % args.stride,
        'display': {'projection': 'XY source', 'xlim': [-5, 5], 'ylim': [-45, 2],
                    'subsampling': 'display only'},
        'excluded_algorithms': ['AutoRails', 'CurveEnvelope', 'detector'],
        'ground_truth': False,
    }
    manifest_path = args.output.with_suffix('.json')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'manifest': str(manifest_path),
                      'selected_frames': len(records)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
