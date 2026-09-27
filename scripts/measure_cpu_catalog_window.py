"""Measure a contiguous C++ CPU CurveRailAxis window from the original archive."""

import argparse
import json
from pathlib import Path

from cpu_catalog_runtime import CpuCatalogRuntime
from serve_stage_2_catalog import ArchiveFrames, experimental_new_data_overlay


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/workspace'))
    parser.add_argument('--first-index', type=int, required=True)
    parser.add_argument('--last-index', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rail-selection-method', choices=('baseline', 'development_candidate'), default='development_candidate')
    parser.add_argument('--rail-forward-min-m', type=float, default=2.0)
    parser.add_argument('--forward-extension-method', choices=('tangent', 'arc_limited'), default='tangent')
    parser.add_argument('--arc-extension-horizon-m', type=float, default=0.0)
    parser.add_argument('--min-arc-radius-m', type=float, default=60.0)
    parser.add_argument('--max-arc-turn-deg', type=float, default=8.0)
    parser.add_argument('--arc-fit-window-pairs', type=int, default=5)
    parser.add_argument('--noise-filter-mode', choices=('legacy', 'candidate_baseline_v2', 'baseline_v3'),
                        default='baseline_v3')
    args = parser.parse_args()
    if args.first_index < 0 or args.last_index < args.first_index:
        raise ValueError('invalid contiguous window')
    overlay = experimental_new_data_overlay(args.root / 'config/geometry_new_data_experiment.yaml')
    archive = ArchiveFrames(args.root / 'dataset/for_hackathon/new_data', overlay)
    if args.last_index >= len(archive.lookup):
        raise IndexError('window exceeds archive frame count')
    runtime = CpuCatalogRuntime(rail_selection_method=args.rail_selection_method,
                                rail_forward_min_m=args.rail_forward_min_m,
                                forward_extension_method=args.forward_extension_method,
                                arc_extension_horizon_m=args.arc_extension_horizon_m,
                                min_arc_radius_m=args.min_arc_radius_m,
                                max_arc_turn_deg=args.max_arc_turn_deg,
                                arc_fit_window_pairs=args.arc_fit_window_pairs,
                                noise_filter_mode=args.noise_filter_mode)
    try:
        results = []
        for index in range(args.first_index, args.last_index + 1):
            record, xyz = archive.frame(index)
            result = runtime.analyze(record, xyz)
            results.append({'index': index, 'status': result['status'],
                            'node_processing_ms': result.get('processing_ms'),
                            'wall_processing_ms': result['wall_processing_ms']})
        node = [item['node_processing_ms'] for item in results if isinstance(item['node_processing_ms'], (int, float))]
        wall = [item['wall_processing_ms'] for item in results]
        output = {'scope': 'CONTIGUOUS_NEW_DATA_DEVELOPMENT_WINDOW_CPU_ONLY', 'compute_backend': 'cpu',
                  'rail_selection_method': args.rail_selection_method,
                  'runtime_transport': runtime.runtime_transport, 'noise_filter_mode': runtime.noise_filter_mode,
                  'rail_search_config': runtime.rail_search_config,
                  'forward_extension_config': runtime.forward_extension_config,
                  'first_index': args.first_index, 'last_index': args.last_index, 'frame_count': len(results),
                  'node_processing_ms': {'p50': percentile(node, .5), 'p95': percentile(node, .95), 'max': max(node)},
                  'wall_processing_ms': {'p50': percentile(wall, .5), 'p95': percentile(wall, .95), 'max': max(wall)},
                  'wall_fps_mean': 1000.0 / (sum(wall) / len(wall)), 'results': results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(output, ensure_ascii=False))
    finally:
        runtime.close()
        archive.close()


if __name__ == '__main__':
    main()
