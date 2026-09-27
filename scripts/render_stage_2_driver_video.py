"""Render doubleT_obstacle as a visual-only LiDAR driver-view MP4."""

import argparse
import json
from pathlib import Path
import sqlite3
import time

import numpy as np
import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud
from stage_2_driver_video import axis_roles, display_sample, driver_projection, reference_gates


def load_driver_view_config(config_path):
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    overlay = config['visualization_overlay']
    envelope = config['universal_fleet_envelope']
    reference = envelope['reference_cross_section']
    if (not overlay.get('enabled') or overlay['status'] != 'UNCONFIRMED' or
            overlay['safety_decision_permitted'] or envelope['safety_decision_permitted'] or
            reference['status'] != 'REFERENCE_ONLY'):
        raise ValueError('driver-view overlay must remain visual-only and non-decision')
    return {
        'roles': axis_roles(overlay['source_axis_assumption']),
        'forward_sign': overlay['source_axis_assumption']['longitudinal_sign'],
        'placement': overlay['placement_in_source_coordinates'],
        'reference': {
            'lateral_min_m': reference['lateral_extent_m']['min'],
            'lateral_max_m': reference['lateral_extent_m']['max'],
            'vertical_min_m': reference['vertical_extent_above_rail_m']['min'],
            'vertical_max_m': reference['vertical_extent_above_rail_m']['max'],
        },
    }


def load_frames(bag):
    databases = list(bag.glob('*.db3'))
    if len(databases) != 1:
        raise ValueError('Expected a directory with exactly one sqlite3 bag database')
    database = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    topics = {row[0]: {'name': row[1], 'type': row[2], 'serialization': row[3]}
              for row in database.execute('select id,name,type,serialization_format from topics')}
    frames, errors = [], []
    for frame_index, (row_id, topic_id, bag_ns, data) in enumerate(
            database.execute('select id,topic_id,timestamp,data from messages order by timestamp,id')):
        try:
            topic = topics[topic_id]
            if topic['type'] != 'sensor_msgs/msg/PointCloud2' or topic['serialization'] != 'cdr':
                raise ValueError('Unsupported topic type or serialization')
            stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
            frames.append((frame_index, bag_ns, stats, xyz))
        except (ValueError, TypeError, RuntimeError) as exc:
            errors.append({'frame_index': frame_index, 'row_id': row_id, 'error': str(exc)})
    database.close()
    return frames, errors, topics


def render_video(frames, output, visual, fps, points_per_frame, minimum_depth_m, maximum_depth_m):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter

    output.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    axis.set_facecolor('#08111f')
    figure.patch.set_facecolor('#08111f')
    gates = reference_gates(visual['roles'], visual['placement'], visual['reference'])
    for gate_x, gate_y in gates:
        axis.plot(gate_x, gate_y, '--', color='crimson', linewidth=1.4, alpha=0.85)
    scatter = axis.scatter([], [], s=1.2, cmap='turbo', vmin=minimum_depth_m,
                         vmax=maximum_depth_m, linewidths=0)
    label = axis.text(0.015, 0.965, '', transform=axis.transAxes, color='white', va='top', fontsize=11)
    axis.text(0.015, 0.02, 'UNCONFIRMED visual assumption: -Y forward, X lateral, Z vertical; '
              'red gates are a reference envelope, not a safety decision',
              transform=axis.transAxes, color='#ff9aa2', va='bottom', fontsize=8)
    axis.set_xlim(-0.75, 0.75)
    axis.set_ylim(-0.35, 0.9)
    axis.set_aspect('equal', adjustable='box')
    axis.set_xlabel('lateral / forward')
    axis.set_ylabel('vertical / forward')
    axis.grid(alpha=0.18, color='white')
    axis.tick_params(colors='white')
    for spine in axis.spines.values():
        spine.set_color('#8090a0')
    writer = FFMpegWriter(fps=fps, codec='libx264', bitrate=3000, extra_args=['-pix_fmt', 'yuv420p'])
    with writer.saving(figure, str(output), dpi=100):
        for frame_index, bag_ns, stats, xyz in frames:
            shown = display_sample(xyz, points_per_frame)
            projected, depth = driver_projection(
                shown, visual['roles'], visual['forward_sign'], minimum_depth_m, maximum_depth_m)
            scatter.set_offsets(projected)
            scatter.set_array(depth)
            label.set_text('doubleT_obstacle  |  frame %04d/%04d  |  %.1f fps  |  %s' %
                           (frame_index, len(frames) - 1, fps, stats['frame']))
            writer.grab_frame()
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--geometry-config', type=Path, default=Path('/app/config/geometry_contract.yaml'))
    parser.add_argument('--fps', type=float, default=10.0)
    parser.add_argument('--points-per-frame', type=int, default=12_000)
    parser.add_argument('--minimum-depth-m', type=float, default=0.25)
    parser.add_argument('--maximum-depth-m', type=float, default=40.0)
    args = parser.parse_args()
    if args.fps <= 0 or args.points_per_frame < 1:
        parser.error('--fps must be positive and --points-per-frame must be at least one')
    visual = load_driver_view_config(args.geometry_config)
    started = time.perf_counter()
    frames, errors, topics = load_frames(args.bag)
    if errors:
        raise RuntimeError('Could not decode every frame: %s' % errors)
    render_video(frames, args.output, visual, args.fps, args.points_per_frame,
                 args.minimum_depth_m, args.maximum_depth_m)
    metadata = {
        'bag': str(args.bag), 'reviewed_frames': len(frames), 'errors': errors, 'topics': topics,
        'fps': args.fps, 'video': args.output.name, 'points_per_frame': args.points_per_frame,
        'visualization_overlay': 'UNCONFIRMED_VISUAL_ONLY', 'safety_decision_permitted': False,
        'wall_seconds': time.perf_counter() - started,
    }
    metadata_path = args.output.with_name('driver_video_metadata.json')
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
