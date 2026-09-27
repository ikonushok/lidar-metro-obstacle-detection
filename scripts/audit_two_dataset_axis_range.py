"""Audit one observed-rail configuration on a complete dataset or contiguous shard.

The evaluator annotations are loaded only after the C++ result is produced.
They are used to report whether an exact selected source return belongs to the
core or margin index lists; they never enter rail selection or envelope logic.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import shutil
import struct
import subprocess
import time

import numpy as np

from archive_bag_frames import ArchiveBagFrames
from cpu_catalog_runtime import CpuCatalogRuntime


DATASETS = {
    'new_data': ('dataset/for_hackathon/new_data', 'new_data'),
    'doubleT_obstacle': ('dataset/for_hackathon/for_hackathon', 'for_hackathon/doubleT_obstacle'),
}


class DirectCpuRuntime:
    """Streams finite XYZ frames through the same C++ rail/envelope cores."""

    def __init__(self, rail_forward_min_m: float):
        self.rail_search_config = {
            'forward_min_m': float(rail_forward_min_m), 'forward_max_m': 80.0,
            'station_length_m': 2.0, 'cell_width_m': 0.04,
        }
        self.process = subprocess.Popen(
            ['ros2', 'run', 'lidar_mosmetro3d_cpp', 'curve_pipeline_stream_cli', str(rail_forward_min_m)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def analyze(self, _record: dict, raw_xyzf: bytes, timeout_seconds: float = 30.0) -> dict:
        del timeout_seconds  # local pipe execution is synchronous; process exit is checked below.
        started = time.monotonic()
        self.process.stdin.write(struct.pack('<Q', len(raw_xyzf) // 12))
        self.process.stdin.write(raw_xyzf)
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read().decode(errors='replace')
            raise RuntimeError(f'direct C++ stream ended unexpectedly: {stderr[-2000:]}')
        result = json.loads(line)
        if result.get('safety_decision_permitted') is not False:
            raise ValueError('direct C++ result must remain candidate-only')
        if result.get('rail_search_config') != self.rail_search_config:
            raise ValueError('direct C++ rail search config does not match request')
        result['wall_processing_ms'] = (time.monotonic() - started) * 1000.0
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.process.kill()


def annotations_for(root: Path, dataset: str) -> dict[int, list[dict]]:
    path = root / 'config/obstacle_annotations_development.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    if document.get('detector_input_permitted') is not False:
        raise ValueError('obstacle annotations must remain evaluator-only')
    if document.get('dataset') != dataset:
        return {}
    output: dict[int, list[dict]] = {}
    for item in document.get('point_annotations', []):
        output.setdefault(int(item['frame_index']), []).append(item)
    return output


def anchor_membership(raw_xyzf: bytes, result: dict, items: list[dict]) -> list[dict]:
    xyz = np.frombuffer(raw_xyzf, dtype='<f4').reshape((-1, 3))
    core = set(result.get('core_source_indices', []))
    margin = set(result.get('margin_source_indices', []))
    output = []
    for item in items:
        anchor = np.array([item['anchor_source_coordinates'][axis] for axis in 'xyz'], dtype=np.float32)
        matches = np.flatnonzero(np.all(np.abs(xyz - anchor) <= 1e-6, axis=1)).tolist()
        if not matches:
            membership = 'SOURCE_POINT_NOT_FOUND'
        elif any(index in core for index in matches):
            membership = 'CORE_INTERSECTION'
        elif any(index in margin for index in matches):
            membership = 'MARGIN_INTERSECTION'
        elif result.get('curve_axis_status') == 'CURVE_AXIS_SUPPORTED':
            membership = 'NOT_CORE_OR_MARGIN_UNRESOLVED'
        else:
            membership = 'UNKNOWN_NO_SUPPORTED_AXIS'
        output.append({'event_id': item['event_id'], 'source_indices': matches, 'membership': membership})
    return output


def compact(index: int, record: dict, raw_xyzf: bytes, result: dict, annotations: list[dict],
            runtime_attempts: int) -> dict:
    stations = [float(pair['source_s_m']) for pair in result.get('rail_pairs_source_xyz', [])]
    support_start = min(stations) if stations else result.get('support_start_s_m')
    support_end = max(stations) if stations else result.get('support_end_s_m')
    return {
        'index': index,
        'header_timestamp_ns': str(record['header_timestamp_ns']),
        'source_frame': record['source_frame'],
        'status': result['status'],
        'reason': result['reason'],
        'axis_supported': result.get('curve_axis_status') == 'CURVE_AXIS_SUPPORTED',
        'support_start_s_m': support_start,
        'support_end_s_m': support_end,
        'rail_pair_count': int(result.get('rail_pair_count', len(stations))),
        'core_count': int(result.get('core_count', 0)),
        'margin_count': int(result.get('margin_count', 0)),
        'outside_reference_count': int(result.get('outside_reference_count', 0)),
        'unknown_count': int(result.get('unknown_count', result.get('point_count', 0))),
        'nearest_intrusion_distance_from_source_origin_m': result.get('nearest_intrusion_distance_from_source_origin_m'),
        'nearest_intrusion_xyz': result.get('nearest_intrusion_xyz'),
        'control_obstacles': anchor_membership(raw_xyzf, result, annotations),
        'runtime_attempts': runtime_attempts,
        'node_processing_ms': result.get('processing_ms'),
        'wall_processing_ms': result.get('wall_processing_ms'),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/workspace'))
    parser.add_argument('--dataset', choices=tuple(DATASETS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--first-index', type=int, default=0)
    parser.add_argument('--last-index', type=int)
    parser.add_argument('--rail-forward-min-m', type=float, default=2.0)
    parser.add_argument('--transport', choices=('ros2', 'direct'), default='ros2')
    parser.add_argument('--skip-control-annotations', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    archive_path, prefix = DATASETS[args.dataset]
    source = ArchiveBagFrames(args.root / archive_path, prefix, args.dataset)
    end = len(source.lookup) - 1 if args.last_index is None else args.last_index
    if args.first_index < 0 or end < args.first_index or end >= len(source.lookup):
        source.close()
        raise IndexError('requested interval is outside dataset')
    evaluation_annotations = annotations_for(args.root, args.dataset)
    if args.transport == 'direct' and evaluation_annotations:
        if not args.skip_control_annotations:
            source.close()
            raise ValueError('direct transport cannot evaluate point annotations; use ros2 or explicitly skip them')
        evaluation_annotations = {}
    runtime = (DirectCpuRuntime(args.rail_forward_min_m) if args.transport == 'direct' else
               CpuCatalogRuntime(rail_selection_method='development_candidate',
                                 rail_forward_min_m=args.rail_forward_min_m))
    rows = []
    try:
        for index in range(args.first_index, end + 1):
            record, raw_xyzf = source.frame(index)
            for runtime_attempts in range(1, 4):
                try:
                    result = runtime.analyze(record, raw_xyzf, timeout_seconds=30.0)
                    break
                except TimeoutError:
                    runtime.close()
                    if runtime_attempts == 3:
                        raise
                    runtime = (DirectCpuRuntime(args.rail_forward_min_m) if args.transport == 'direct' else
                               CpuCatalogRuntime(rail_selection_method='development_candidate',
                                                 rail_forward_min_m=args.rail_forward_min_m))
            rows.append(compact(index, record, raw_xyzf, result,
                                evaluation_annotations.get(index, []), runtime_attempts))
            if len(rows) % 100 == 0:
                print(json.dumps({'dataset': args.dataset, 'completed': len(rows), 'last_index': index}), flush=True)
    except Exception:
        shutil.rmtree(args.output, ignore_errors=True)
        raise
    finally:
        runtime.close()
        source.close()

    args.output.mkdir(parents=True)
    with gzip.open(args.output / 'per_frame.jsonl.gz', 'wt', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
    supported = [row for row in rows if row['axis_supported']]
    controls = [control | {'frame_index': row['index']} for row in rows for control in row['control_obstacles']]
    summary = {
        'format': 'observed-rail-axis-range-audit-v1',
        'scope': 'DEVELOPMENT_TWO_DATASET_OBSERVED_RAIL_AUDIT',
        'dataset': args.dataset,
        'source_archive': archive_path,
        'frame_interval_inclusive': [args.first_index, end],
        'frame_count': len(rows),
        'rail_selection_method': 'development_candidate',
        'rail_search_config': runtime.rail_search_config,
        'execution_transport': args.transport,
        'supported_frame_count': len(supported),
        'unknown_frame_count': len(rows) - len(supported),
        'status_counts': dict(Counter(row['status'] for row in rows)),
        'reason_counts': dict(Counter(row['reason'] for row in rows)),
        'support_start_min_s_m': min((row['support_start_s_m'] for row in supported), default=None),
        'support_end_max_s_m': max((row['support_end_s_m'] for row in supported), default=None),
        'frames_supporting_at_least_56_m': sum(row['support_end_s_m'] >= 56.0 for row in supported),
        'frames_supporting_at_least_60_m': sum(row['support_end_s_m'] >= 60.0 for row in supported),
        'core_candidate_frame_count': sum(row['core_count'] > 0 for row in rows),
        'core_return_count_total': sum(row['core_count'] for row in rows),
        'control_obstacles': controls,
        'safety_decision_permitted': False,
        'annotations_are_detector_input': False,
        'control_annotations_evaluated': not args.skip_control_annotations,
        'limitations': [
            'CORE_RETURNS_ARE_CANDIDATES_AND_MAY_INCLUDE_NORMAL_INFRASTRUCTURE',
            'NO_OBJECT_LEVEL_GROUND_TRUTH_FOR_NEW_DATA',
            'UNKNOWN_NEVER_MEANS_CLEAR',
            'NO_AXIS_EXTRAPOLATION',
        ],
    }
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
