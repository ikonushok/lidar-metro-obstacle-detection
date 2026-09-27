"""Render raw source cloud plus stored C++ bag-screen output; no detector here."""
import argparse
import json
from pathlib import Path
import sqlite3

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud


def read_raw(bag, index):
    database = next(bag.glob('*.db3'))
    connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        row = connection.execute('select data from messages order by timestamp,id limit 1 offset ?', (index,)).fetchone()
        if row is None:
            raise IndexError(index)
        _stats, xyz = inspect_cloud(deserialize_message(row[0], PointCloud2))
        return xyz
    finally:
        connection.close()


def draw_envelope(axis, pairs, bounds):
    if len(pairs) < 2 or not bounds:
        return
    left_bound, right_bound = bounds[:2]
    centers = np.asarray([[(a + b) / 2 for a, b in zip(pair['left_xyz'], pair['right_xyz'])] for pair in pairs])
    left = np.asarray([pair['left_xyz'] for pair in pairs])
    for a, b, side in zip(centers, centers[1:], left):
        direction = b[:2] - a[:2]
        length = np.linalg.norm(direction)
        if not length:
            continue
        normal = np.array([direction[1], -direction[0]]) / length
        if np.dot(normal, side[:2] - a[:2]) < 0:
            normal = -normal
        polygon = np.vstack((a[:2] + normal * left_bound, a[:2] + normal * right_bound,
                             b[:2] + normal * right_bound, b[:2] + normal * left_bound,
                             a[:2] + normal * left_bound))
        axis.plot(polygon[:, 0], -polygon[:, 1], color='#f6f6f6', lw=.7, alpha=.9)


def draw(axis, raw, row, method):
    cpp = row['cpp']
    shown = raw[::max(1, len(raw) // 40000)]
    axis.scatter(shown[:, 0], -shown[:, 1], s=.25, color='#8493a0', alpha=.22, linewidths=0)
    core = np.asarray(cpp.get('core_source_indices', []), dtype=np.int64)
    if core.size:
        axis.scatter(raw[core, 0], -raw[core, 1], s=.6, color='#ff3f58', alpha=.7, linewidths=0,
                     label='C++ CORE returns')
    pairs = cpp.get('rail_pairs_source_xyz', [])
    color = '#4ea8de' if method == 'baseline' else '#e63946'
    if pairs:
        left = np.asarray([pair['left_xyz'] for pair in pairs])
        right = np.asarray([pair['right_xyz'] for pair in pairs])
        center = (left + right) / 2
        axis.plot(left[:, 0], -left[:, 1], color=color, lw=1.0)
        axis.plot(right[:, 0], -right[:, 1], color=color, lw=1.0)
        axis.plot(center[:, 0], -center[:, 1], color='#ffd34f', lw=1.8, label='C++ CurveRailAxis')
        draw_envelope(axis, pairs, cpp.get('core_bounds_source_axis'))
        axis.scatter([center[0, 0], center[-1, 0]], [-center[0, 1], -center[-1, 1]], marker='|',
                     s=30, color='#65ed9c', label='support boundaries')
    axis.set_title('%s: %s\n%s' % (method, cpp.get('curve_axis_status'), cpp.get('reason')), fontsize=8)
    axis.set(xlim=(-5, 5), ylim=(0, 48), xlabel='X source units', ylabel='−Y source units')
    axis.grid(alpha=.16)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--bag', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--indices', type=int, nargs='+', default=[0, 500, 850, 876])
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    data = json.loads(args.manifest.read_text(encoding='utf-8'))
    by_method = {method: {row['index']: row for row in rows} for method, rows in data['methods'].items()}
    args.output.mkdir(parents=True)
    rendered = []
    for index in args.indices:
        raw = read_raw(args.bag, index)
        figure, axes = plt.subplots(1, 2, figsize=(13, 7), sharex=True, sharey=True, constrained_layout=True)
        for axis, method in zip(axes, ('baseline', 'development_candidate')):
            draw(axis, raw, by_method[method][index], method)
        figure.suptitle(
            'bag frame %d: raw source returns + exact stored C++ result\n'
            'Grey = display-decimated raw; red = C++ CORE; white = C++ core envelope. '
            'Support is geometry only, not proof of observed/clear space.' % index, fontsize=10)
        handles, labels = axes[1].get_legend_handles_labels()
        figure.legend(handles, labels, loc='lower center', ncol=3, fontsize=8)
        image = args.output / ('bag_%04d_cpp_comparison.png' % index)
        figure.savefig(image, dpi=210)
        plt.close(figure)
        rendered.append({'index': index, 'image': image.name,
                         'source': 'stored C++ node JSON + exact finite nonzero raw source returns'})
    (args.output / 'manifest.json').write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
