"""Offline geometry-first gate with a small ML suppressor for uncertain CORE components.

The strong geometry gate is deliberately not controlled by ML:

* high-support CORE components are obstacle candidates unless they match an
  explicit boundary-warning rule for known outside/above gabarit shapes;
* the learned tree only decides whether lower-support uncertain components
  should be allowed through as extra obstacle alarms.

This script is for offline candidate screening only. It does not change runtime
behavior and never turns a negative model result into a safety CLEAR decision.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from typing import Any


POSITIVE_CLASS = "positive_target"
NEGATIVE_CLASS = "negative_boundary"

FEATURE_NAMES = (
    "point_count",
    "extent_x_m",
    "extent_y_m",
    "extent_z_m",
    "centroid_x_m",
    "centroid_y_m",
    "centroid_z_m",
    "nearest_distance_m",
    "s_span_m",
    "min_s_m",
    "max_s_m",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_interval(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    first, last = int(value[0]), int(value[1])
    if last < first:
        raise ValueError(f"invalid interval {value!r}")
    return first, last


def iter_events(labels: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    for source in labels.get("sources", []):
        if source.get("source_id") == source_id:
            return list(source.get("events", []))
    raise KeyError(f"source_id {source_id!r} missing in labels")


def event_windows(labels: dict[str, Any], source_id: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    positives: list[tuple[int, int]] = []
    boundaries: list[tuple[int, int]] = []
    for event in iter_events(labels, source_id):
        interval = normalize_interval(event.get("frame_interval"))
        if interval is None:
            continue
        if event.get("expected_class") == POSITIVE_CLASS:
            positives.append(interval)
        elif event.get("expected_class") == NEGATIVE_CLASS:
            boundaries.append(interval)
    return positives, boundaries


def in_windows(frame: int, windows: list[tuple[int, int]]) -> bool:
    return any(first <= frame <= last for first, last in windows)


def in_buffer(frame: int, windows: list[tuple[int, int]], padding: int) -> bool:
    return any(first - padding <= frame <= last + padding for first, last in windows)


def component_is_boundary_warning(row: dict[str, Any]) -> bool:
    centroid = row.get("centroid_xyz") or [None, None, None]
    extent = row.get("extent_xyz_m") or [None, None, None]
    if any(value is None for value in (centroid[0], centroid[2], extent[0], extent[1], extent[2])):
        return False
    left_thin_tall = (
        float(centroid[0]) < -1.30
        and float(extent[0]) < 0.25
        and float(extent[2]) > 1.50
    )
    upper_broad_above = (
        float(centroid[2]) > 1.00
        and float(extent[0]) > 1.00
        and float(extent[1]) > 1.00
        and float(extent[2]) > 0.30
    )
    return left_thin_tall or upper_broad_above


def features(row: dict[str, Any]) -> list[float]:
    extent = row.get("extent_xyz_m") or [0.0, 0.0, 0.0]
    centroid = row.get("centroid_xyz") or [0.0, 0.0, 0.0]
    min_s = row.get("min_s_m")
    max_s = row.get("max_s_m")
    min_s_f = 0.0 if min_s is None else float(min_s)
    max_s_f = min_s_f if max_s is None else float(max_s)
    return [
        float(row.get("point_count", 0)),
        float(extent[0]),
        float(extent[1]),
        float(extent[2]),
        float(centroid[0]),
        float(centroid[1]),
        float(centroid[2]),
        float(row.get("nearest_distance_m") or 0.0),
        max_s_f - min_s_f,
        min_s_f,
        max_s_f,
    ]


def gini(positive: float, negative: float) -> float:
    total = positive + negative
    if total <= 0.0:
        return 0.0
    return 1.0 - (positive / total) ** 2 - (negative / total) ** 2


def make_tree(rows: list[dict[str, Any]], depth: int, max_depth: int, min_leaf: int) -> dict[str, Any]:
    positive = sum(row["weight"] for row in rows if row["label"])
    negative = sum(row["weight"] for row in rows if not row["label"])
    node: dict[str, Any] = {"positive_weight": positive, "negative_weight": negative}
    if depth >= max_depth or len(rows) < 2 * min_leaf or not positive or not negative:
        return node
    parent_gini = gini(positive, negative)
    best: tuple[float, int, float, list[dict[str, Any]], list[dict[str, Any]]] | None = None
    for feature_index in range(len(FEATURE_NAMES)):
        values = sorted({row["features"][feature_index] for row in rows})
        if len(values) < 2:
            continue
        positions = sorted({
            min(len(values) - 2, round((len(values) - 1) * part / 24))
            for part in range(1, 24)
        })
        for position in positions:
            threshold = (values[position] + values[position + 1]) * 0.5
            left = [row for row in rows if row["features"][feature_index] <= threshold]
            right = [row for row in rows if row["features"][feature_index] > threshold]
            if len(left) < min_leaf or len(right) < min_leaf:
                continue
            left_pos = sum(row["weight"] for row in left if row["label"])
            left_neg = sum(row["weight"] for row in left if not row["label"])
            right_pos = positive - left_pos
            right_neg = negative - left_neg
            total = positive + negative
            gain = parent_gini - (
                ((left_pos + left_neg) / total) * gini(left_pos, left_neg)
                + ((right_pos + right_neg) / total) * gini(right_pos, right_neg)
            )
            if best is None or gain > best[0]:
                best = (gain, feature_index, threshold, left, right)
    if best is None or best[0] <= 1e-9:
        return node
    _gain, feature_index, threshold, left, right = best
    node.update(
        {
            "feature": FEATURE_NAMES[feature_index],
            "threshold": threshold,
            "left": make_tree(left, depth + 1, max_depth, min_leaf),
            "right": make_tree(right, depth + 1, max_depth, min_leaf),
        }
    )
    return node


def predict_probability(tree: dict[str, Any], values: list[float]) -> float:
    node = tree
    positions = {name: index for index, name in enumerate(FEATURE_NAMES)}
    while "feature" in node:
        node = node["left"] if values[positions[node["feature"]]] <= node["threshold"] else node["right"]
    total = node["positive_weight"] + node["negative_weight"]
    return 0.0 if total <= 0.0 else node["positive_weight"] / total


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


def build_training_rows(
    components: list[dict[str, Any]],
    labels: dict[str, Any],
    source_id: str,
    uncertain_min_points: int,
    strong_min_points: int,
    buffer_frames: int,
) -> list[dict[str, Any]]:
    positives, boundaries = event_windows(labels, source_id)
    all_label_windows = positives + boundaries
    rows = []
    for row in components:
        if row.get("zone", "core") != "core":
            continue
        point_count = int(row.get("point_count", 0))
        if point_count < uncertain_min_points or point_count >= strong_min_points:
            continue
        frame = int(row["frame"])
        if in_windows(frame, positives):
            label = True
            source = "positive_event_window"
        elif in_windows(frame, boundaries):
            label = False
            source = "boundary_event_window"
        elif not in_buffer(frame, all_label_windows, buffer_frames):
            label = False
            source = "background_outside_label_buffer"
        else:
            continue
        rows.append(
            {
                "frame": frame,
                "label": label,
                "label_source": source,
                "features": features(row),
                "point_count": point_count,
            }
        )
    counts = Counter(row["label"] for row in rows)
    if not counts[True] or not counts[False]:
        raise ValueError(f"training needs both classes, got {dict(counts)}")
    for row in rows:
        row["weight"] = 0.5 / counts[row["label"]]
    return rows


def evaluate_alarm_frames(
    labels: dict[str, Any],
    source_id: str,
    alarm_frames: set[int],
) -> dict[str, Any]:
    event_rows = []
    for event in iter_events(labels, source_id):
        interval = normalize_interval(event.get("frame_interval"))
        frames = (
            sorted(frame for frame in alarm_frames if interval[0] <= frame <= interval[1])
            if interval is not None else []
        )
        expected = event.get("expected_class")
        passed = None
        if interval is not None and expected == POSITIVE_CLASS:
            passed = bool(frames)
        elif interval is not None and expected == NEGATIVE_CLASS:
            passed = not bool(frames)
        event_rows.append(
            {
                "event_id": event["event_id"],
                "organizer_order": event.get("organizer_order"),
                "expected_class": expected,
                "frame_interval": list(interval) if interval else None,
                "alarm_frames_in_window": frames,
                "passed_expected_class": passed,
            }
        )
    positive = [
        row for row in event_rows
        if row["expected_class"] == POSITIVE_CLASS and row["frame_interval"] is not None
    ]
    boundary = [
        row for row in event_rows
        if row["expected_class"] == NEGATIVE_CLASS and row["frame_interval"] is not None
    ]
    assigned = set()
    for row in positive + boundary:
        first, last = row["frame_interval"]
        assigned.update(frame for frame in alarm_frames if first <= frame <= last)
    return {
        "positive_target_events_hit": sum(row["passed_expected_class"] is True for row in positive),
        "positive_target_events_scorable": len(positive),
        "negative_boundary_false_positive_events": sum(row["passed_expected_class"] is False for row in boundary),
        "negative_boundary_events_scorable": len(boundary),
        "alarm_frame_count": len(alarm_frames),
        "unassigned_alarm_frame_count": len(alarm_frames - assigned),
        "alarm_runs": summarize_runs(sorted(alarm_frames)),
        "event_results": event_rows,
    }


def build_frames(
    components: list[dict[str, Any]],
    tree: dict[str, Any],
    threshold: float,
    strong_min_points: int,
    uncertain_min_points: int,
) -> tuple[list[dict[str, Any]], dict[str, set[int]]]:
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in components:
        if row.get("zone", "core") == "core":
            by_frame[int(row["frame"])].append(row)
    max_frame = max(by_frame, default=-1)
    fields = {
        "geometry_gate_obstacle": set(),
        "geometry_boundary_warning": set(),
        "ml_uncertain_obstacle": set(),
        "geometry_gate_ml_suppressor_obstacle": set(),
    }
    frame_rows = []
    for frame in range(max_frame + 1):
        strong_obstacle = []
        boundary_warning = []
        ml_uncertain = []
        scored_uncertain = []
        for row in by_frame.get(frame, []):
            point_count = int(row.get("point_count", 0))
            is_boundary = component_is_boundary_warning(row)
            if point_count >= uncertain_min_points and is_boundary:
                boundary_warning.append(row)
            if point_count >= strong_min_points:
                if not is_boundary:
                    strong_obstacle.append(row)
                continue
            if point_count >= uncertain_min_points and not is_boundary:
                probability = predict_probability(tree, features(row))
                scored_uncertain.append({"point_count": point_count, "probability": round(probability, 6)})
                if probability >= threshold:
                    ml_uncertain.append(row)
        if strong_obstacle:
            fields["geometry_gate_obstacle"].add(frame)
            fields["geometry_gate_ml_suppressor_obstacle"].add(frame)
        if boundary_warning:
            fields["geometry_boundary_warning"].add(frame)
        if ml_uncertain:
            fields["ml_uncertain_obstacle"].add(frame)
            fields["geometry_gate_ml_suppressor_obstacle"].add(frame)
        frame_rows.append(
            {
                "index": frame,
                "geometry_gate_obstacle": bool(strong_obstacle),
                "geometry_boundary_warning": bool(boundary_warning),
                "ml_uncertain_obstacle": bool(ml_uncertain),
                "geometry_gate_ml_suppressor_obstacle": bool(strong_obstacle or ml_uncertain),
                "strong_obstacle_component_count": len(strong_obstacle),
                "boundary_warning_component_count": len(boundary_warning),
                "ml_uncertain_component_count": len(ml_uncertain),
                "scored_uncertain_top": sorted(
                    scored_uncertain, key=lambda item: item["probability"], reverse=True
                )[:5],
            }
        )
    return frame_rows, fields


def calibrate_threshold(
    components: list[dict[str, Any]],
    tree: dict[str, Any],
    labels: dict[str, Any],
    source_id: str,
    strong_min_points: int,
    uncertain_min_points: int,
) -> dict[str, Any]:
    scores = {
        predict_probability(tree, features(row))
        for row in components
        if row.get("zone", "core") == "core"
        and uncertain_min_points <= int(row.get("point_count", 0)) < strong_min_points
        and not component_is_boundary_warning(row)
    }
    thresholds = sorted(scores | {0.0, 0.5, 1.0, max(scores, default=0.0) + 1e-6})
    best = None
    candidates = []
    for threshold in thresholds:
        _rows, fields = build_frames(components, tree, threshold, strong_min_points, uncertain_min_points)
        metric = evaluate_alarm_frames(labels, source_id, fields["geometry_gate_ml_suppressor_obstacle"])
        candidate = {
            "threshold": threshold,
            **{key: metric[key] for key in (
                "positive_target_events_hit",
                "positive_target_events_scorable",
                "negative_boundary_false_positive_events",
                "negative_boundary_events_scorable",
                "alarm_frame_count",
                "unassigned_alarm_frame_count",
            )},
        }
        candidates.append(candidate)
        key = (
            -candidate["positive_target_events_hit"],
            candidate["negative_boundary_false_positive_events"],
            candidate["unassigned_alarm_frame_count"],
            candidate["alarm_frame_count"],
            -threshold,
        )
        if best is None or key < best["selection_key"]:
            best = {**candidate, "selection_key": key}
    assert best is not None
    return {"best": best, "candidates": candidates}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--model-in", type=Path)
    parser.add_argument("--strong-min-points", type=int, default=1000)
    parser.add_argument("--uncertain-min-points", type=int, default=250)
    parser.add_argument("--buffer-frames", type=int, default=10)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--min-leaf", type=int, default=20)
    parser.add_argument("--threshold", type=float)
    args = parser.parse_args()

    components = load_json(args.components)
    labels = load_json(args.labels) if args.labels else None
    if args.model_in:
        model = load_json(args.model_in)
        tree = model["tree"]
        threshold = float(args.threshold if args.threshold is not None else model["selected_threshold"])
        training_summary = model.get("training")
        calibration = None
    else:
        if labels is None:
            raise ValueError("--labels is required when training a model")
        training_rows = build_training_rows(
            components,
            labels,
            args.source_id,
            args.uncertain_min_points,
            args.strong_min_points,
            args.buffer_frames,
        )
        tree = make_tree(training_rows, 0, args.max_depth, args.min_leaf)
        calibration = calibrate_threshold(
            components,
            tree,
            labels,
            args.source_id,
            args.strong_min_points,
            args.uncertain_min_points,
        )
        threshold = float(args.threshold if args.threshold is not None else calibration["best"]["threshold"])
        counts = Counter(row["label"] for row in training_rows)
        training_summary = {
            "source_id": args.source_id,
            "rows": len(training_rows),
            "class_counts": {"positive": counts[True], "negative": counts[False]},
            "label_sources": dict(Counter(row["label_source"] for row in training_rows)),
            "features": list(FEATURE_NAMES),
            "max_depth": args.max_depth,
            "min_leaf": args.min_leaf,
            "buffer_frames": args.buffer_frames,
            "note": (
                "Positive component labels are weak labels from event windows; "
                "cloud_with_fake_obj remains development/calibration evidence."
            ),
        }

    frame_rows, fields = build_frames(
        components,
        tree,
        threshold,
        args.strong_min_points,
        args.uncertain_min_points,
    )
    eval_summary = (
        {
            name: evaluate_alarm_frames(labels, args.source_id, alarms)
            for name, alarms in fields.items()
        }
        if labels is not None else None
    )
    args.output.mkdir(parents=True, exist_ok=True)
    model_payload = {
        "format": "geometry_gate_ml_suppressor_tree_v1",
        "scope": "OFFLINE_CANDIDATE_SCREENING_NOT_RUNTIME_OR_SAFETY_DECISION",
        "strong_geometry_gate": {
            "strong_min_points": args.strong_min_points,
            "boundary_rule": (
                "outside-left thin/tall: centroid_x < -1.30 and extent_x < 0.25 "
                "and extent_z > 1.50; upper/above broad: centroid_z > 1.00 "
                "and extent_x > 1.00 and extent_y > 1.00 and extent_z > 0.30"
            ),
            "ml_may_suppress_strong_geometry": False,
        },
        "uncertain_component_range": [args.uncertain_min_points, args.strong_min_points - 1],
        "selected_threshold": threshold,
        "tree": tree,
        "training": training_summary,
        "calibration": calibration,
        "limitations": [
            "ML is trained from weak event-window labels, not box-level GT.",
            "A negative model result does not mean CLEAR.",
            "Strong geometry positives are preserved before ML.",
        ],
    }
    (args.output / "model.json").write_text(
        json.dumps(model_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "frames.json").write_text(
        json.dumps(frame_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "format": "geometry_gate_ml_suppressor_summary_v1",
        "source_id": args.source_id,
        "selected_threshold": threshold,
        "training": training_summary,
        "calibration_best": calibration["best"] if calibration else None,
        "alarm_frames": {
            name: {"count": len(alarms), "runs": summarize_runs(sorted(alarms))}
            for name, alarms in fields.items()
        },
        "event_eval": eval_summary,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "threshold": threshold}, ensure_ascii=False))


if __name__ == "__main__":
    main()
