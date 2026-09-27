"""Measure one declared Stage 3 development frame window from recorded outputs."""

import argparse
import json
from pathlib import Path

from stage_3_metrics import summarize_window


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--first-frame', type=int, required=True)
    parser.add_argument('--last-frame', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = [json.loads(line) for line in args.results.read_text(encoding='utf-8').splitlines()
               if line.strip()]
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    summary = summarize_window(results, manifest['frames'], args.first_frame, args.last_frame)
    summary['results_path'] = str(args.results)
    summary['manifest_path'] = str(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
