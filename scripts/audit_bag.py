"""Read every cloud through Humble deserialization, preserving source clocks."""
import argparse
import json
from pathlib import Path
import platform
import resource
import sqlite3
import time
import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2
from cloud_input import inspect_cloud


def plot_cloud(xyz, path, title):
    import matplotlib.pyplot as plt
    # Display subsampling only; statistics above use all points.
    shown = xyz[::max(1, len(xyz) // 40000)]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (a, b) in zip(axes, [(0, 1), (0, 2), (1, 2)]):
        ax.scatter(shown[:, a], shown[:, b], s=.15, alpha=.45)
        ax.set_xlabel('XYZ'[a] + ' (source units)')
        ax.set_ylabel('XYZ'[b] + ' (source units)')
        ax.set_aspect('equal', adjustable='datalim')
        ax.grid(alpha=.2)
    fig.suptitle(title + '\nFinite nonzero points; axes and units NOT calibrated')
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('bag', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    files = list(args.bag.glob('*.db3'))
    if len(files) != 1:
        p.error('Stage 1 audit expects a directory with exactly one sqlite3 bag database')
    args.output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(files[0].resolve().as_uri() + '?mode=ro', uri=True)
    topics = {r[0]: {'name': r[1], 'type': r[2], 'serialization': r[3], 'qos': r[4]}
              for r in db.execute('select id,name,type,serialization_format,offered_qos_profiles from topics')}
    total = db.execute('select count(*) from messages').fetchone()[0]
    errors, timings, frames, schemas = [], [], set(), set()
    totals = {k: 0 for k in ('points', 'finite', 'zero', 'nonfinite', 'nonzero_finite')}
    previous_header = None
    header_decreases = 0
    started = time.perf_counter()
    with (args.output / 'frames.jsonl').open('w') as stream:
        for i, (rowid, topicid, bag_ns, data) in enumerate(db.execute('select id,topic_id,timestamp,data from messages order by timestamp,id')):
            begin = time.perf_counter()
            try:
                topic = topics[topicid]
                if topic['type'] != 'sensor_msgs/msg/PointCloud2' or topic['serialization'] != 'cdr':
                    raise ValueError('Unsupported type or serialization')
                msg = deserialize_message(data, PointCloud2)
                stats, xyz = inspect_cloud(msg)
                elapsed = (time.perf_counter() - begin) * 1000
                timings.append(elapsed)
                frames.add(stats['frame'])
                schemas.add(json.dumps([stats['fields'], stats['point_step'], stats['bigendian']]))
                for k in totals:
                    totals[k] += stats[k]
                if previous_header is not None and stats['header_ns'] < previous_header:
                    header_decreases += 1
                previous_header = stats['header_ns']
                stream.write(json.dumps(dict(stats, rowid=rowid, topic=topic['name'], bag_ns=bag_ns, inspection_ms=elapsed)) + '\n')
                if i in (0, total // 2, total - 1):
                    plot_cloud(xyz, args.output / ('cloud_%04d.png' % i), '%s | frame %d | %s' % (args.bag.name, i, stats['frame']))
            except (ValueError, TypeError, RuntimeError) as exc:
                errors.append(dict(rowid=rowid, error=str(exc)))
            if (i + 1) % 50 == 0:
                print('Inspected', i + 1, '/', total, flush=True)
    summary = dict(bag=str(args.bag), database_messages=total, inspected=len(timings), errors=errors,
                   topics=topics, frames=sorted(frames), distinct_schemas=len(schemas), totals=totals,
                   header_decreases=header_decreases, order='bag timestamp, id',
                   inspection_ms_p50=float(np.percentile(timings, 50)) if timings else None,
                   inspection_ms_p95=float(np.percentile(timings, 95)) if timings else None,
                   wall_seconds=time.perf_counter()-started,
                   peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                   python=platform.python_version(), platform=platform.platform(),
                   decision='UNKNOWN: geometry not calibrated; detector not implemented',
                   timing_scope='offline deserialize + input inspection, not detector or replay latency')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    db.close()
    return bool(errors) or len(timings) != total


if __name__ == '__main__':
    raise SystemExit(main())
