"""Enrich saved results with supplemental components, preserving baseline evidence."""
import json
from pathlib import Path
import time
import numpy as np
from stage_3_baseline import candidate_envelope_masks, protrusion_clusters, load_geometry_contract


def main():
    root = Path('/workspace')
    output = root / 'artefacts/stage_3/stage_3_results.jsonl'
    results = [json.loads(line) for line in output.read_text().splitlines()]
    player = root / 'artefacts/stage_2/player_doubleT_obstacle'
    manifest = json.loads((player / 'manifest.json').read_text())
    config = load_geometry_contract(root / 'config/geometry_contract.yaml')
    assert len(results) == len(manifest['frames'])
    for index, (result, frame) in enumerate(zip(results, manifest['frames'])):
        assert result['header_timestamp_ns'] == frame['header_timestamp_ns']
        assert result['source_frame'] == frame['source_frame']
        xyz = np.fromfile(player / frame['file'], dtype='<f4').reshape(-1, 3)
        start = time.perf_counter()
        masks = candidate_envelope_masks(xyz, config)
        result['protrusion_clusters'] = protrusion_clusters(xyz[masks[1]], config, masks[4])
        result['supplemental_offline_processing_ms'] = (time.perf_counter()-start)*1000
        result['processing_ms_scope'] = 'ORIGINAL_BASELINE_REPLAY_EXCLUDING_OFFLINE_SUPPLEMENT'
        result['protrusion_parameters'] = config['detection']['protrusion_segmentation']
        if index % 50 == 0:
            print('Supplemented frame', index, flush=True)
    temporary = output.with_suffix('.protrusions.tmp')
    temporary.write_text(''.join(json.dumps(r)+'\n' for r in results), encoding='utf-8')
    temporary.replace(output)
    print('Completed', len(results), 'frames; original clusters and processing evidence retained', flush=True)


if __name__ == '__main__':
    main()
