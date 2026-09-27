"""Evaluate detector outputs against working obstacle event labels.

This is an offline benchmark helper. It does not change runtime detector
behavior and does not make a safety CLEAR decision.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any


POSITIVE_CLASS = "positive_target"
NEGATIVE_CLASS = "negative_boundary"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_interval(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"frame_interval must be null or [first,last], got {value!r}")
    first, last = int(value[0]), int(value[1])
    if last < first:
        raise ValueError(f"invalid frame interval {value!r}")
    return first, last


def expand_interval(interval: tuple[int, int], padding: int) -> tuple[int, int]:
    return max(0, interval[0] - padding), interval[1] + padding


def iter_events(labels: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    for source in labels.get("sources", []):
        if source.get("source_id") == source_id:
            return list(source.get("events", []))
    raise KeyError(f"source_id {source_id!r} is not present in labels")


def frame_number(row: dict[str, Any]) -> int:
    if "index" in row:
        return int(row["index"])
    if "frame" in row:
        return int(row["frame"])
    raise KeyError("frame row has neither 'index' nor 'frame'")


def detector_series_from_frames(frames_path: Path, fields: list[str]) -> dict[str, set[int]]:
    frames = load_json(frames_path)
    if not isinstance(frames, list):
        raise ValueError("--frames must point to a JSON list")
    series: dict[str, set[int]] = {field: set() for field in fields}
    for row in frames:
        frame = frame_number(row)
        for field in fields:
            if bool(row.get(field)):
                series[field].add(frame)
    return series


def detector_series_from_components(components_path: Path, thresholds: list[int]) -> dict[str, set[int]]:
    components = load_json(components_path)
    if not isinstance(components, list):
        raise ValueError("--components must point to a JSON list")
    series: dict[str, set[int]] = {f"raw_core_component_ge_{threshold}": set() for threshold in thresholds}
    for row in components:
        frame = int(row["frame"])
        point_count = int(row["point_count"])
        for threshold in thresholds:
            if point_count >= threshold:
                series[f"raw_core_component_ge_{threshold}"].add(frame)
    return series


def summarize_runs(indices: list[int]) -> list[dict[str, int]]:
    if not indices:
        return []
    runs = []
    start = prev = indices[0]
    for value in indices[1:]:
        if value == prev + 1:
            prev = value
            continue
        runs.append({"start": start, "end": prev, "count": prev - start + 1})
        start = prev = value
    runs.append({"start": start, "end": prev, "count": prev - start + 1})
    return runs


def evaluate_series(events: list[dict[str, Any]], alarm_frames: set[int], padding: int) -> dict[str, Any]:
    event_rows = []
    scorable_windows: list[tuple[int, int, str]] = []
    for event in events:
        interval = normalize_interval(event.get("frame_interval"))
        window = expand_interval(interval, padding) if interval is not None else None
        frames_in_window = (
            sorted(frame for frame in alarm_frames if window[0] <= frame <= window[1])
            if window is not None else []
        )
        expected_class = event.get("expected_class")
        hit = None
        if expected_class == POSITIVE_CLASS and window is not None:
            hit = bool(frames_in_window)
        elif expected_class == NEGATIVE_CLASS and window is not None:
            hit = not bool(frames_in_window)
        if window is not None:
            scorable_windows.append((window[0], window[1], event["event_id"]))
        event_rows.append({
            "event_id": event["event_id"],
            "organizer_order": event.get("organizer_order"),
            "expected_class": expected_class,
            "matching_status": event.get("matching_status"),
            "frame_interval": event.get("frame_interval"),
            "scoring_window": list(window) if window is not None else None,
            "alarm_frames_in_window": frames_in_window,
            "alarm_runs_in_window": summarize_runs(frames_in_window),
            "passed_expected_class": hit,
        })

    positive_events = [event for event in events if event.get("expected_class") == POSITIVE_CLASS]
    negative_events = [event for event in events if event.get("expected_class") == NEGATIVE_CLASS]
    scorable_positive = [row for row in event_rows if row["expected_class"] == POSITIVE_CLASS and row["scoring_window"]]
    scorable_negative = [row for row in event_rows if row["expected_class"] == NEGATIVE_CLASS and row["scoring_window"]]
    positive_hits = [row for row in scorable_positive if row["passed_expected_class"] is True]
    boundary_fp = [
        row for row in scorable_negative
        if row["passed_expected_class"] is False
    ]

    assigned_alarm_frames = set()
    assigned_by_event: dict[int, list[str]] = defaultdict(list)
    for first, last, event_id in scorable_windows:
        for frame in alarm_frames:
            if first <= frame <= last:
                assigned_alarm_frames.add(frame)
                assigned_by_event[frame].append(event_id)
    unassigned_alarm_frames = sorted(alarm_frames - assigned_alarm_frames)

    return {
        "positive_target_events_total": len(positive_events),
        "positive_target_events_scorable": len(scorable_positive),
        "positive_target_events_hit": len(positive_hits),
        "positive_target_events_missed": len(scorable_positive) - len(positive_hits),
        "positive_target_events_unlocalized": len(positive_events) - len(scorable_positive),
        "negative_boundary_events_total": len(negative_events),
        "negative_boundary_events_scorable": len(scorable_negative),
        "negative_boundary_false_positive_events": len(boundary_fp),
        "alarm_frame_count": len(alarm_frames),
        "alarm_runs": summarize_runs(sorted(alarm_frames)),
        "unassigned_alarm_frame_count": len(unassigned_alarm_frames),
        "unassigned_alarm_frame_examples": unassigned_alarm_frames[:100],
        "event_results": event_rows,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    labels = load_json(args.labels)
    events = iter_events(labels, args.source_id)
    detector_series: dict[str, set[int]] = {}
    if args.frames is not None:
        detector_series.update(detector_series_from_frames(args.frames, args.detector_field))
    if args.components is not None:
        detector_series.update(detector_series_from_components(args.components, args.component_threshold))
    if not detector_series:
        raise ValueError("provide --frames and/or --components")

    result = {
        "format": "working_obstacle_event_eval_v1",
        "scope": "OFFLINE_EVENT_BENCHMARK_NOT_RUNTIME_OR_SAFETY_DECISION",
        "labels": str(args.labels),
        "source_id": args.source_id,
        "window_padding_frames": args.window_padding_frames,
        "decision_rule": labels.get("decision_rule"),
        "detectors": {},
        "limitations": [
            "cloud_with_fake_obj labels are working labels from organizer description plus project localization, not final box-level GT.",
            "Events with null frame_interval are counted in totals but excluded from localized hit/miss scoring.",
            "UNKNOWN is not CLEAR; this evaluator only scores supplied alarm series against event windows.",
        ],
    }
    for name, alarm_frames in sorted(detector_series.items()):
        result["detectors"][name] = evaluate_series(events, alarm_frames, args.window_padding_frames)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "detectors": list(result["detectors"])}, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--frames", type=Path)
    parser.add_argument("--components", type=Path)
    parser.add_argument("--detector-field", action="append",
                        default=["causal_temporal_alarm", "frame_model_alarm"])
    parser.add_argument("--component-threshold", action="append", type=int, default=[])
    parser.add_argument("--window-padding-frames", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.window_padding_frames < 0:
        raise ValueError("--window-padding-frames must be non-negative")
    if args.components is not None and not args.component_threshold:
        args.component_threshold = [22]
    evaluate(args)


if __name__ == "__main__":
    main()
