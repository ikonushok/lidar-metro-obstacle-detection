"""Legacy entrypoint: check generic obstacle anchors against candidate components."""
import json
from pathlib import Path
import numpy as np
from stage_3_baseline import candidate_envelope_masks, load_geometry_contract, voxel_components, protrusion_clusters


def main():
    root = Path('/workspace')
    annotations = json.loads((root / 'config/obstacle_annotations_development.json').read_text())
    player = root / 'artefacts/stage_2/player_doubleT_obstacle'
    manifest = json.loads((player / 'manifest.json').read_text())
    config = load_geometry_contract(root / 'config/geometry_contract.yaml')
    saved = [json.loads(line) for line in (root / 'artefacts/stage_3/stage_3_results.jsonl').read_text().splitlines()]
    evidence = []
    for event in annotations['point_annotations']:
        index = event['frame_index']
        frame = manifest['frames'][index]
        assert frame['header_timestamp_ns'] == event['header_timestamp_ns'] == saved[index]['header_timestamp_ns']
        assert frame['source_frame'] == event['source_frame'] == saved[index]['source_frame']
        xyz = np.fromfile(player / frame['file'], dtype='<f4').reshape(-1, 3)
        anchor = np.array([event['anchor_source_coordinates'][axis] for axis in 'xyz'])
        matched = np.flatnonzero(np.linalg.norm(xyz - anchor, axis=1) < 1e-6)
        assert len(matched), 'Anchor is not a source return'
        masks = candidate_envelope_masks(xyz, config)
        candidates = xyz[masks[1]]
        selected_indices = np.flatnonzero(masks[1])
        component_info = None
        for indices in voxel_components(candidates, config['detection']['clustering']['voxel_size_m']):
            if not np.isin(selected_indices[indices], matched).any():
                continue
            points = candidates[indices]
            bounds = {axis: {'min': float(points[:, i].min()), 'max': float(points[:, i].max())}
                      for i, axis in enumerate('xyz')}
            saved_matches = [i for i, cluster in enumerate(saved[index]['clusters'])
                             if cluster['bounds_source_coordinates'] == bounds]
            component_info = {'points': len(indices), 'bounds': bounds,
                              'saved_cluster_indices_with_identical_bounds': saved_matches}
            break
        protrusions = protrusion_clusters(candidates, config, masks[4])
        anchor_protrusions = [c for c in protrusions if all(
            c['bounds_source_coordinates'][axis]['min'] <= anchor[i] <=
            c['bounds_source_coordinates'][axis]['max'] for i, axis in enumerate('xyz'))]
        evidence.append({'event_id': event['event_id'], 'frame': index,
                         'protrusion_count': len(protrusions),
                         'protrusion_bounds_containing_anchor': anchor_protrusions,
                         'distance_to_anchor_m': float(np.linalg.norm(anchor)),
                         'anchor_in_candidate_mask': bool(masks[1][matched].any()),
                         'component': component_info})
    output = root / 'artefacts/stage_3/metrics/obstacle_anchor_check.json'
    output.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
