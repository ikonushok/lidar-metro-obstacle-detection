"""Merge contiguous observed-rail audit shards and recompute aggregate counts."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    with gzip.open(path / 'per_frame.jsonl.gz', 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shard', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    summaries = [json.loads((path / 'summary.json').read_text(encoding='utf-8')) for path in args.shard]
    reference = summaries[0]
    keys = ('format', 'dataset', 'source_archive', 'rail_selection_method', 'rail_search_config')
    if any(any(summary.get(key) != reference.get(key) for key in keys) for summary in summaries[1:]):
        raise ValueError('shards do not share one audit contract')
    rows = sorted((row for path in args.shard for row in load_rows(path)), key=lambda row: row['index'])
    if not rows or any(next_row['index'] != row['index'] + 1 for row, next_row in zip(rows, rows[1:])):
        raise ValueError('shard frame ranges are not contiguous')
    supported = [row for row in rows if row['axis_supported']]
    controls = [control | {'frame_index': row['index']} for row in rows for control in row['control_obstacles']]
    merged = dict(reference)
    merged.update({
        'frame_interval_inclusive': [rows[0]['index'], rows[-1]['index']],
        'frame_count': len(rows),
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
        'merged_from_shards': [str(path) for path in args.shard],
    })
    args.output.mkdir(parents=True)
    with gzip.open(args.output / 'per_frame.jsonl.gz', 'wt', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
    (args.output / 'summary.json').write_text(json.dumps(merged, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(merged, ensure_ascii=False))


if __name__ == '__main__':
    main()
