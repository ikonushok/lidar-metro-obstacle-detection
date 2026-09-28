"""Evaluate baseline_v3 TP/TN/FP/FN for replay sources.

Run inside the project Docker image after sourcing ROS and the package setup:

  python3 /workspace/scripts/evaluate_baseline_v3_metrics.py --root /workspace

The primary table intentionally excludes synthetic_no100 because it is a
component-level development probe, not a replay bag evaluated with the same
unit as the listed sources.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import time
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
for extra in (SCRIPT_DIR, REPO_DIR / "src"):
    text = str(extra)
    if text not in sys.path:
        sys.path.insert(0, text)

from archive_bag_frames import ArchiveBagFrames
from cpu_catalog_runtime import DirectDetailedCpuRuntime


@dataclass
class Metrics:
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    frames_evaluated: int = 0
    events_evaluated: int = 0
    notes: list[str] = field(default_factory=list)

    def add(self, gt_positive: bool, alarm: bool) -> None:
        if gt_positive and alarm:
            self.tp += 1
        elif gt_positive and not alarm:
            self.fn += 1
        elif not gt_positive and alarm:
            self.fp += 1
        else:
            self.tn += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "tn": self.tn,
            "fp": self.fp,
            "fn": self.fn,
            "frames_evaluated": self.frames_evaluated,
            "events_evaluated": self.events_evaluated,
            "notes": self.notes,
        }


def make_runtime() -> DirectDetailedCpuRuntime:
    return DirectDetailedCpuRuntime(
        rail_selection_method="development_candidate",
        rail_forward_min_m=2.0,
        forward_extension_method="tangent",
        noise_filter_mode="baseline_v3",
    )


def detector_alarm(result: dict[str, Any]) -> bool:
    return result.get("intrusion_candidate_present") is True


def positive_frame(source: dict[str, Any], index: int) -> bool:
    for start, end in source.get("positive_frames_inclusive", []):
        if int(start) <= index <= int(end):
            return True
    return False


def frame_range(total: int, start: int | None, end: int | None) -> tuple[int, int]:
    first = 0 if start is None else start
    last = total - 1 if end is None else end
    if first < 0 or last < first or last >= total:
        raise ValueError(f"invalid frame range {first}..{last} for total={total}")
    return first, last


def evaluate_frame_source(
    root: Path,
    source: dict[str, Any],
    *,
    start: int | None,
    end: int | None,
    progress_every: int,
) -> Metrics:
    bag = ArchiveBagFrames(root / source["archive"], source["bag_prefix"], source["source_id"])
    runtime = make_runtime()
    metrics = Metrics()
    started = time.monotonic()
    try:
        first, last = frame_range(len(bag.lookup), start, end)
        warmup_first = max(0, first - 1) if first > 0 else first
        if warmup_first != first:
            metrics.notes.append("partial range used one warm-up frame for temporal continuity")
        for index in range(warmup_first, last + 1):
            record, xyz = bag.frame(index)
            result = runtime.analyze(record, xyz)
            if index < first:
                continue
            metrics.add(positive_frame(source, index), detector_alarm(result))
            metrics.frames_evaluated += 1
            if progress_every and metrics.frames_evaluated % progress_every == 0:
                elapsed = time.monotonic() - started
                print(
                    f"progress {source['source_id']}: "
                    f"{metrics.frames_evaluated}/{last - first + 1} frames, {elapsed:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        runtime.close()
        bag.close()
    return metrics


def event_frame_indexes(source: dict[str, Any]) -> set[int]:
    indexes: set[int] = set()
    for group in ("positive_events", "negative_events"):
        for event in source.get(group, []):
            start, end = event["frames_inclusive"]
            indexes.update(range(int(start), int(end) + 1))
    return indexes


def evaluate_event_source(root: Path, source: dict[str, Any], *, progress_every: int) -> Metrics:
    bag = ArchiveBagFrames(root / source["archive"], source["bag_prefix"], source["source_id"])
    runtime = make_runtime()
    hits: dict[str, bool] = {}
    needed = event_frame_indexes(source)
    metrics = Metrics(notes=[source.get("label_status", "event-window labels")])
    started = time.monotonic()
    try:
        for index in range(len(bag.lookup)):
            record, xyz = bag.frame(index)
            result = runtime.analyze(record, xyz)
            got = detector_alarm(result)
            if index in needed:
                for group in ("positive_events", "negative_events"):
                    for event in source.get(group, []):
                        event_id = event["event_id"]
                        start, end = event["frames_inclusive"]
                        if int(start) <= index <= int(end):
                            hits[event_id] = hits.get(event_id, False) or got
            if progress_every and (index + 1) % progress_every == 0:
                elapsed = time.monotonic() - started
                print(
                    f"progress {source['source_id']}: {index + 1}/{len(bag.lookup)} frames, {elapsed:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        runtime.close()
        bag.close()

    for event in source.get("positive_events", []):
        metrics.add(True, hits.get(event["event_id"], False))
        metrics.events_evaluated += 1
    for event in source.get("negative_events", []):
        metrics.add(False, hits.get(event["event_id"], False))
        metrics.events_evaluated += 1
    metrics.frames_evaluated = len(bag.lookup)
    return metrics


def evaluate_source(
    root: Path,
    source: dict[str, Any],
    *,
    start: int | None,
    end: int | None,
    progress_every: int,
) -> Metrics:
    if source["kind"] == "frame":
        return evaluate_frame_source(root, source, start=start, end=end, progress_every=progress_every)
    if source["kind"] == "event_window":
        if start is not None or end is not None:
            raise ValueError("start/end are only supported for frame sources")
        return evaluate_event_source(root, source, progress_every=progress_every)
    raise ValueError(f"unsupported source kind: {source['kind']}")


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = ["| dataset | TP | TN | FP | FN |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        metrics = row["metrics"]
        lines.append(
            f"| `{row['source_id']}` | {metrics['tp']} | {metrics['tn']} | "
            f"{metrics['fp']} | {metrics['fn']} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--labels", type=Path, default=Path("config/evaluation_labels.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artefacts/current_model_validation"))
    parser.add_argument("--source", action="append", help="source_id to evaluate; may be repeated")
    parser.add_argument("--start", type=int, help="first frame index, only with one frame source")
    parser.add_argument("--end", type=int, help="last frame index inclusive, only with one frame source")
    parser.add_argument("--progress-every", type=int, default=250, help="print progress every N frames; 0 disables it")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    labels_path = args.labels if args.labels.is_absolute() else root / args.labels
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    sources = labels["sources"]
    requested = set(args.source or [source["source_id"] for source in sources])
    selected = [source for source in sources if source["source_id"] in requested]
    missing = requested - {source["source_id"] for source in selected}
    if missing:
        raise SystemExit(f"unknown source_id: {', '.join(sorted(missing))}")
    if (args.start is not None or args.end is not None) and len(selected) != 1:
        raise SystemExit("--start/--end require exactly one --source")

    rows: list[dict[str, Any]] = []
    for source in selected:
        metrics = evaluate_source(
            root,
            source,
            start=args.start,
            end=args.end,
            progress_every=args.progress_every,
        )
        row = {"source_id": source["source_id"], "kind": source["kind"], "metrics": metrics.as_dict()}
        rows.append(row)
        print(
            f"{source['source_id']}\tTP={metrics.tp}\tTN={metrics.tn}\tFP={metrics.fp}\tFN={metrics.fn}",
            flush=True,
        )

    totals = Metrics()
    for row in rows:
        metrics = row["metrics"]
        totals.tp += metrics["tp"]
        totals.tn += metrics["tn"]
        totals.fp += metrics["fp"]
        totals.fn += metrics["fn"]
        totals.frames_evaluated += metrics["frames_evaluated"]
        totals.events_evaluated += metrics["events_evaluated"]

    report = {
        "format": "baseline_v3_primary_metrics_v1",
        "labels": str(labels_path),
        "policy": labels.get("policy", {}),
        "rows": rows,
        "totals": totals.as_dict(),
    }

    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "baseline_v3_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "baseline_v3_metrics.md").write_text(markdown_table(rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
