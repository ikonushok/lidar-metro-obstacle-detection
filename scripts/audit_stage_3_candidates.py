"""Build a browser-readable source-coordinate recurrence audit from Stage 3 outputs."""

import argparse
import json
from pathlib import Path

from stage_3_candidate_audit import audit_source_coordinate_recurrence, full_cloud_clusters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--first-frame', type=int, required=True)
    parser.add_argument('--last-frame', type=int, required=True)
    parser.add_argument('--voxel-size-m', type=float, default=0.5)
    parser.add_argument('--minimum-recurrence-fraction', type=float, default=0.8)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--full-cloud', action='store_true',
                        help='Audit all displayed cloud returns, independent of detector envelope.')
    parser.add_argument('--geometry-config', type=Path, default=Path('/app/config/geometry_contract.yaml'))
    args = parser.parse_args()
    results = [json.loads(line) for line in args.results.read_text(encoding='utf-8').splitlines()
               if line.strip()]
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    if args.full_cloud:
        import numpy as np
        import yaml
        config = yaml.safe_load(args.geometry_config.read_text(encoding='utf-8'))
        clustering = config['detection']['clustering']
        for index in range(args.first_frame, args.last_frame + 1):
            frame = manifest['frames'][index]
            points = np.fromfile(args.manifest.parent / frame['file'], dtype='<f4').reshape(-1, 3)
            results[index] = dict(results[index], clusters=full_cloud_clusters(
                points, clustering['voxel_size_m'], clustering['min_cluster_points'],
                config['detection']['roi']['forward_max_m']))
    audit = audit_source_coordinate_recurrence(
        results, manifest['frames'], args.first_frame, args.last_frame,
        args.voxel_size_m, args.minimum_recurrence_fraction)
    audit['results_path'] = str(args.results)
    audit['manifest_path'] = str(args.manifest)
    audit['input_scope'] = 'FULL_CLOUD' if args.full_cloud else 'DETECTION_CANDIDATES_ONLY'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'frame_window_inclusive': audit['frame_window_inclusive'],
        'groups': len(audit['groups']),
        'recurrent_groups': len(audit['recurrent_groups']),
        'output': str(args.output),
        'scope': audit['scope'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
