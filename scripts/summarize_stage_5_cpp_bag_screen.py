"""Summarize an existing Stage-5 C++ bag screen; no geometry is recomputed."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def support(row):
    pairs = row['cpp'].get('rail_pairs_source_xyz', [])
    stations = [float(pair['source_s_m']) for pair in pairs]
    return (min(stations), max(stations)) if stations else (None, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding='utf-8'))
    baseline = {int(row['index']): row for row in data['methods']['baseline']}
    candidate = {int(row['index']): row for row in data['methods']['development_candidate']}
    if baseline.keys() != candidate.keys():
        raise ValueError('baseline/candidate frame sets differ')
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in sorted(baseline):
        old, new = baseline[index], candidate[index]
        old_start, old_end = support(old)
        new_start, new_end = support(new)
        rows.append({
            'index': index,
            'baseline_axis_status': old['cpp'].get('curve_axis_status'),
            'candidate_axis_status': new['cpp'].get('curve_axis_status'),
            'baseline_reason': old['cpp'].get('reason'),
            'candidate_reason': new['cpp'].get('reason'),
            'baseline_pairs': old['cpp'].get('rail_pair_count', 0),
            'candidate_pairs': new['cpp'].get('rail_pair_count', 0),
            'baseline_support_start_s_m': old_start, 'baseline_support_end_s_m': old_end,
            'candidate_support_start_s_m': new_start, 'candidate_support_end_s_m': new_end,
            'baseline_core_count': old['cpp'].get('core_count'),
            'candidate_core_count': new['cpp'].get('core_count'),
            'baseline_unknown_count': old['cpp'].get('unknown_count', old['cpp'].get('point_count')),
            'candidate_unknown_count': new['cpp'].get('unknown_count', new['cpp'].get('point_count')),
            'candidate_added_support': old['cpp'].get('curve_axis_status') != 'CURVE_AXIS_SUPPORTED' and
                                       new['cpp'].get('curve_axis_status') == 'CURVE_AXIS_SUPPORTED',
            'axis_status_changed': old['cpp'].get('curve_axis_status') != new['cpp'].get('curve_axis_status'),
        })
    fields = list(rows[0]) if rows else []
    with (args.output / 'per_frame.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        'input_manifest': str(args.manifest), 'frame_count': len(rows),
        'baseline_supported': sum(row['baseline_axis_status'] == 'CURVE_AXIS_SUPPORTED' for row in rows),
        'candidate_supported': sum(row['candidate_axis_status'] == 'CURVE_AXIS_SUPPORTED' for row in rows),
        'candidate_added_support_indices': [row['index'] for row in rows if row['candidate_added_support']],
        'axis_status_changed_indices': [row['index'] for row in rows if row['axis_status_changed']],
        'status_counts': {method: dict(Counter(item['cpp'].get('curve_axis_status')
                                                for item in values))
                          for method, values in data['methods'].items()},
        'unknown_reason_counts': {method: dict(Counter(item['cpp'].get('reason') for item in values
                                                        if item['cpp'].get('curve_axis_status') != 'CURVE_AXIS_SUPPORTED'))
                                  for method, values in data['methods'].items()},
        'not_ground_truth': True,
        'not_switch_confirmation': True,
    }
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
