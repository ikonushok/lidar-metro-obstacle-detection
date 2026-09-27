"""Compare geometry outputs from two axis-audit execution transports."""
import argparse
import gzip
import json
from pathlib import Path


FIELDS = (
    'index', 'status', 'reason', 'axis_supported', 'support_start_s_m', 'support_end_s_m',
    'rail_pair_count', 'core_count', 'margin_count', 'outside_reference_count', 'unknown_count',
    'nearest_intrusion_distance_from_source_origin_m', 'nearest_intrusion_xyz',
)


def load(path: Path):
    with gzip.open(path / 'per_frame.jsonl.gz', 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('left', type=Path)
    parser.add_argument('right', type=Path)
    args = parser.parse_args()
    left, right = load(args.left), load(args.right)
    if len(left) != len(right):
        raise ValueError('frame counts differ')
    mismatches = []
    for a, b in zip(left, right):
        changed = {field: [a.get(field), b.get(field)] for field in FIELDS if a.get(field) != b.get(field)}
        if changed:
            mismatches.append({'index': a.get('index'), 'changed': changed})
    result = {'frame_count': len(left), 'matched_frame_count': len(left) - len(mismatches),
              'mismatch_count': len(mismatches), 'mismatches': mismatches[:10]}
    print(json.dumps(result, ensure_ascii=False))
    if mismatches:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
