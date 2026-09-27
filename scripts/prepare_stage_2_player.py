"""Prepare full PointCloud2 frames for the visual-only Stage 2 web player."""

import argparse
import json
from pathlib import Path
import shutil
import sqlite3

import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud
from stage_2_driver_video import axis_roles
from stage_2_player import (PLAYER_FORMAT_VERSION, encode_xyz_frame, frame_record,
                            load_stage_3_results, visual_reference_crop)


def load_visual_contract(config_path):
    """Read only the explicitly non-decision visualization overlay."""
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    overlay = config['visualization_overlay']
    envelope = config['universal_fleet_envelope']
    reference = envelope['reference_cross_section']
    if (not overlay.get('enabled') or overlay['status'] != 'UNCONFIRMED' or
            overlay['safety_decision_permitted'] or envelope['safety_decision_permitted'] or
            reference['status'] != 'REFERENCE_ONLY'):
        raise ValueError('Player overlay must remain visual-only and non-decision')
    axis_roles(overlay['source_axis_assumption'])
    return {
        'status': 'UNCONFIRMED',
        'label': 'UNCONFIRMED / manual review only',
        'safety_decision_permitted': False,
        'source_axis_assumption': overlay['source_axis_assumption'],
        'placement_in_source_coordinates': overlay['placement_in_source_coordinates'],
        'reference_cross_section': {
            'status': reference['status'],
            'coordinate_system': reference['coordinate_system'],
            'units': reference['units'],
            'lateral_extent_m': reference['lateral_extent_m'],
            'vertical_extent_above_rail_m': reference['vertical_extent_above_rail_m'],
        },
    }


def read_bag_frames(bag):
    databases = list(bag.glob('*.db3'))
    if len(databases) != 1:
        raise ValueError('Expected a directory with exactly one sqlite3 bag database')
    connection = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    topics = {
        row[0]: {'name': row[1], 'type': row[2], 'serialization': row[3]}
        for row in connection.execute('select id,name,type,serialization_format from topics')
    }
    try:
        for frame_index, (row_id, topic_id, bag_ns, data) in enumerate(connection.execute(
                'select id,topic_id,timestamp,data from messages order by timestamp,id')):
            topic = topics[topic_id]
            if topic['type'] != 'sensor_msgs/msg/PointCloud2' or topic['serialization'] != 'cdr':
                raise ValueError('Unsupported topic type or serialization at bag row %s' % row_id)
            try:
                stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
            except (TypeError, ValueError, RuntimeError) as exc:
                raise ValueError('Could not decode bag row %s: %s' % (row_id, exc)) from exc
            yield frame_index, bag_ns, stats, xyz, topic
    finally:
        connection.close()


def copy_static_assets(web_source, output):
    vendor = output / 'vendor'
    vendor.mkdir(parents=True, exist_ok=True)
    candidates = [
        (Path('/usr/share/javascript/three/three.min.js'), vendor / 'three.min.js'),
        (Path('/usr/share/javascript/three/examples/js/controls/OrbitControls.js'),
         vendor / 'OrbitControls.js'),
    ]
    absent = [str(source) for source, _ in candidates if not source.is_file()]
    if absent:
        raise FileNotFoundError('Missing packaged Three.js assets: %s' % ', '.join(absent))
    shutil.copyfile(web_source, output / 'index.html')
    for source, destination in candidates:
        shutil.copyfile(source, destination)


def prepare_player(bag, output, geometry_config, web_source, stage_3_results=None):
    output.mkdir(parents=True, exist_ok=True)
    frames_dir = output / 'frames'
    frames_dir.mkdir(parents=True, exist_ok=True)
    copy_static_assets(web_source, output)
    visual_contract = load_visual_contract(geometry_config)

    records, topic_names, first_bag_ns = [], set(), None
    for frame_index, bag_ns, stats, xyz, topic in read_bag_frames(bag):
        if first_bag_ns is None:
            first_bag_ns = bag_ns
        filename = 'frame_%04d.xyzf' % frame_index
        (frames_dir / filename).write_bytes(encode_xyz_frame(xyz))
        records.append(frame_record(frame_index, bag_ns, stats, xyz, first_bag_ns,
                                    'frames/' + filename))
        topic_names.add(topic['name'])

    if not records:
        raise ValueError('Bag has no PointCloud2 frames')
    stage_3_attached = load_stage_3_results(stage_3_results, records)
    manifest = {
        'format': 'lidar-mosmetro3d.xyzf',
        'format_version': PLAYER_FORMAT_VERSION,
        'dataset': bag.name,
        'frame_count': len(records),
        'topics': sorted(topic_names),
        'point_encoding': {
            'layout': 'little-endian float32 x,y,z triples',
            'bytes_per_point': 12,
            'decimation': 'NONE',
            'included_returns': 'all finite, non-zero XYZ returns in source order',
            'excluded_returns': 'non-finite values and (0,0,0) no-return placeholders only',
        },
        'visualization_overlay': visual_contract,
        'visualization_crop': visual_reference_crop(visual_contract),
        'safety_decision_permitted': False,
        'stage_3_baseline_attached': stage_3_attached,
        'frames': records,
    }
    (output / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def attach_stage_3_to_existing_manifest(output, stage_3_results, web_source):
    """Reuse intact player frames and attach only recorded Stage 3 metadata."""
    manifest_path = output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('safety_decision_permitted') is not False:
        raise ValueError('Existing player manifest must remain visual-only')
    copy_static_assets(web_source, output)
    manifest['stage_3_baseline_attached'] = load_stage_3_results(
        stage_3_results, manifest['frames'])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--geometry-config', type=Path,
                        default=Path('/app/config/geometry_contract.yaml'))
    parser.add_argument('--web-source', type=Path, default=Path('/app/web/stage_2_player.html'))
    parser.add_argument('--stage-3-results', type=Path)
    parser.add_argument('--attach-stage-3-to-existing-manifest', action='store_true')
    args = parser.parse_args()
    if args.attach_stage_3_to_existing_manifest:
        if args.stage_3_results is None:
            parser.error('--attach-stage-3-to-existing-manifest requires --stage-3-results')
        manifest = attach_stage_3_to_existing_manifest(args.output, args.stage_3_results,
                                                        args.web_source)
    else:
        manifest = prepare_player(args.bag, args.output, args.geometry_config, args.web_source,
                                  args.stage_3_results)
    print(json.dumps({
        'prepared_frames': manifest['frame_count'],
        'output': str(args.output),
        'decimation': manifest['point_encoding']['decimation'],
        'safety_decision_permitted': manifest['safety_decision_permitted'],
        'stage_3_baseline_attached': manifest['stage_3_baseline_attached'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
