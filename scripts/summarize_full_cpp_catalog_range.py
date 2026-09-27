"""Summarize observed rail support from an existing full C++ catalog."""
import argparse
import gzip
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.catalog / 'catalog_manifest.json').read_text(encoding='utf-8'))
    rows = []
    for part in manifest['parts']:
        with gzip.open(args.catalog / part['catalog_file'], 'rt', encoding='utf-8') as stream:
            for line in stream:
                item = json.loads(line)
                support = item['support']
                rows.append((int(item['index']), support.get('start_source_s_m'), support.get('end_source_s_m')))
    rows.sort()
    if not rows or rows[0][0] != 0 or rows[-1][0] != manifest['frame_count'] - 1 or any(
            following[0] != current[0] + 1 for current, following in zip(rows, rows[1:])):
        raise ValueError('catalog frame coverage is not complete and contiguous')
    supported = [row for row in rows if row[1] is not None and row[2] is not None]
    summary = {
        'source_catalog': str(args.catalog),
        'frame_interval_inclusive': [rows[0][0], rows[-1][0]],
        'frame_count': len(rows),
        'rail_selection_method': manifest['rail_selection_method'],
        'rail_search_config': 'LEGACY_DEFAULT_NOT_ECHOED_IN_RESULT; forward_min_m=3.0 from matching source revision',
        'supported_frame_count': len(supported),
        'support_start_min_s_m': min(row[1] for row in supported),
        'support_end_max_s_m': max(row[2] for row in supported),
        'frames_supporting_at_least_56_m': sum(row[2] >= 56.0 for row in supported),
        'frames_supporting_at_least_60_m': sum(row[2] >= 60.0 for row in supported),
        'status_counts': manifest['status_counts'],
        'reason_counts': manifest['reason_counts'],
        'core_returns_total': manifest['core_returns_total'],
        'safety_decision_permitted': False,
    }
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
