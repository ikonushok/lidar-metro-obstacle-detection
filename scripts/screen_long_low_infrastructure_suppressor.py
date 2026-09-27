"""Screen an offline suppressor for long low infrastructure-like components.

The suppressor is calibrated only as an offline diagnostic. It removes strong
geometry alarms caused solely by very elongated, low, side-offset CORE
components. It never changes UNKNOWN handling and is not runtime code.
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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_runs(indices: list[int]) -> list[dict[str, int]]:
    if not indices:
        return []
    runs = []
    start = previous = indices[0]
    for value in indices[1:]:
        if value == previous + 1:
            previous = value
            continue
        runs.append({"start": start, "end": previous, "count": previous - start + 1})
        start = previous = value
    runs.append({"start": start, "end": previous, "count": previous - start + 1})
    return runs


def component_features(row: dict[str, Any]) -> dict[str, float]:
    extent = [float(value) for value in row.get("extent_xyz_m", [0.0, 0.0, 0.0])]
    centroid = [float(value) for value in row.get("centroid_xyz", [0.0, 0.0, 0.0])]
    min_s = row.get("min_s_m")
    max_s = row.get("max_s_m")
    min_s_f = 0.0 if min_s is None else float(min_s)
    max_s_f = min_s_f if max_s is None else float(max_s)
    return {
        "point_count": float(row.get("point_count", 0)),
        "extent_x_m": extent[0],
        "extent_y_m": extent[1],
        "extent_z_m": extent[2],
        "centroid_x_m": centroid[0],
        "centroid_y_m": centroid[1],
        "centroid_z_m": centroid[2],
        "s_span_m": max_s_f - min_s_f,
        "nearest_distance_m": float(row.get("nearest_distance_m") or 0.0),
    }


def is_long_low_infrastructure(row: dict[str, Any], args: argparse.Namespace) -> bool:
    values = component_features(row)
    if values["point_count"] < args.strong_min_points:
        return False
    if values["extent_y_m"] < args.min_extent_y_m:
        return False
    if values["extent_z_m"] > args.max_extent_z_m:
        return False
    if values["extent_x_m"] > args.max_extent_x_m:
        return False
    if abs(values["centroid_x_m"]) < args.min_abs_centroid_x_m:
        return False
    if values["s_span_m"] < args.min_s_span_m:
        return False
    if values["extent_x_m"] > 1e-9 and values["extent_y_m"] / values["extent_x_m"] < args.min_y_to_x_ratio:
        return False
    if values["extent_z_m"] > 1e-9 and values["extent_y_m"] / values["extent_z_m"] < args.min_y_to_z_ratio:
        return False
    return True


def core_components_by_frame(components: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in components:
        if row.get("zone", "core") == "core":
            by_frame[int(row["frame"])].append(row)
    return by_frame


def suppressed_geometry_frames(
    components: list[dict[str, Any]],
    gate_frames: list[dict[str, Any]],
    args: argparse.Namespace,
) -> tuple[set[int], set[int], list[dict[str, Any]]]:
    by_frame = core_components_by_frame(components)
    before = {
        int(row["index"])
        for row in gate_frames
        if row.get("geometry_gate_ml_suppressor_obstacle")
    }
    after = set()
    removed_details = []
    for row in gate_frames:
        frame = int(row["index"])
        if frame not in before:
            continue
        strong = [
            component for component in by_frame.get(frame, [])
            if int(component.get("point_count", 0)) >= args.strong_min_points
        ]
        suppressible = [component for component in strong if is_long_low_infrastructure(component, args)]
        has_unsuppressed_strong = any(component not in suppressible for component in strong)
        has_ml_uncertain = bool(row.get("ml_uncertain_obstacle"))
        if has_unsuppressed_strong or has_ml_uncertain:
            after.add(frame)
            continue
        if suppressible:
            removed_details.append(
                {
                    "frame": frame,
                    "suppressed_component_count": len(suppressible),
                    "top_suppressed": [
                        {
                            "point_count": int(component["point_count"]),
                            **component_features(component),
                        }
                        for component in sorted(
                            suppressible,
                            key=lambda item: int(item.get("point_count", 0)),
                            reverse=True,
                        )[:3]
                    ],
                }
            )
            continue
        after.add(frame)
    return before, after, removed_details


def normalize_interval(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    return int(value[0]), int(value[1])


def iter_events(labels: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    for source in labels.get("sources", []):
        if source.get("source_id") == source_id:
            return list(source.get("events", []))
    return []


def event_eval(labels: dict[str, Any], source_id: str, frames: set[int]) -> dict[str, Any]:
    rows = []
    for event in iter_events(labels, source_id):
        interval = normalize_interval(event.get("frame_interval"))
        hits = []
        if interval is not None:
            first, last = interval
            hits = sorted(frame for frame in frames if first <= frame <= last)
        expected = event.get("expected_class")
        passed = None
        if interval is not None and expected == POSITIVE_CLASS:
            passed = bool(hits)
        elif interval is not None and expected == NEGATIVE_CLASS:
            passed = not bool(hits)
        rows.append(
            {
                "event_id": event.get("event_id"),
                "organizer_order": event.get("organizer_order"),
                "expected_class": expected,
                "frame_interval": list(interval) if interval else None,
                "alarm_frames_in_window": hits,
                "passed_expected_class": passed,
            }
        )
    positives = [row for row in rows if row["expected_class"] == POSITIVE_CLASS and row["frame_interval"]]
    negatives = [row for row in rows if row["expected_class"] == NEGATIVE_CLASS and row["frame_interval"]]
    return {
        "positive_target_events_hit": sum(row["passed_expected_class"] is True for row in positives),
        "positive_target_events_scorable": len(positives),
        "positive_target_events_missed": sum(row["passed_expected_class"] is False for row in positives),
        "negative_boundary_false_positive_events": sum(row["passed_expected_class"] is False for row in negatives),
        "negative_boundary_events_scorable": len(negatives),
        "event_results": rows,
    }


def doublet_eval(frames: set[int]) -> dict[str, Any]:
    positive = set(range(13, 65))
    outside = frames - positive
    return {
        "positive_frames_hit": len(frames & positive),
        "positive_frames_total": len(positive),
        "missing_positive_frames": sorted(positive - frames),
        "outside_alarm_frames": len(outside),
        "outside_alarm_examples": sorted(outside)[:30],
    }


def load_gate_frames(path: Path) -> list[dict[str, Any]]:
    return load_json(path)


def screen_old_negative_sources(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = []
    root = args.old_negative_root
    for components_path in sorted((root / "raw_core_60m").glob("*/components.json")):
        source_id = components_path.parent.name
        components = load_json(components_path)
        gate_frames = load_gate_frames(root / "gate_ml_apply" / source_id / "frames.json")
        before, after, removed = suppressed_geometry_frames(components, gate_frames, args)
        summary = {
            "source": source_id,
            "geometry_fp_before": len(before),
            "geometry_fp_after": len(after),
            "geometry_fp_removed": len(before - after),
            "removed_runs": summarize_runs(sorted(before - after)),
            "removed_examples": removed[:20],
        }
        rows.append(summary)
    totals = {
        "geometry_fp_before": sum(row["geometry_fp_before"] for row in rows),
        "geometry_fp_after": sum(row["geometry_fp_after"] for row in rows),
        "geometry_fp_removed": sum(row["geometry_fp_removed"] for row in rows),
    }
    return rows, totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-negative-root", type=Path, required=True)
    parser.add_argument("--cloud-components", type=Path, required=True)
    parser.add_argument("--cloud-gate-frames", type=Path, required=True)
    parser.add_argument("--doublet-components", type=Path, required=True)
    parser.add_argument("--doublet-gate-frames", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--strong-min-points", type=int, default=1000)
    parser.add_argument("--min-extent-y-m", type=float, default=8.0)
    parser.add_argument("--max-extent-z-m", type=float, default=0.35)
    parser.add_argument("--max-extent-x-m", type=float, default=0.60)
    parser.add_argument("--min-abs-centroid-x-m", type=float, default=1.0)
    parser.add_argument("--min-s-span-m", type=float, default=8.0)
    parser.add_argument("--min-y-to-x-ratio", type=float, default=25.0)
    parser.add_argument("--min-y-to-z-ratio", type=float, default=25.0)
    args = parser.parse_args()

    old_rows, old_totals = screen_old_negative_sources(args)

    labels = load_json(args.labels)
    cloud_components = load_json(args.cloud_components)
    cloud_gate_frames = load_gate_frames(args.cloud_gate_frames)
    cloud_before, cloud_after, cloud_removed = suppressed_geometry_frames(cloud_components, cloud_gate_frames, args)
    cloud_eval_before = event_eval(labels, "cloud_with_fake_obj", cloud_before)
    cloud_eval_after = event_eval(labels, "cloud_with_fake_obj", cloud_after)

    doublet_components = load_json(args.doublet_components)
    doublet_gate_frames = load_gate_frames(args.doublet_gate_frames)
    doublet_before, doublet_after, doublet_removed = suppressed_geometry_frames(
        doublet_components, doublet_gate_frames, args
    )
    doublet_eval_before = doublet_eval(doublet_before)
    doublet_eval_after = doublet_eval(doublet_after)

    payload = {
        "format": "long_low_infrastructure_suppressor_screen_v1",
        "scope": "OFFLINE_CALIBRATION_SCREENING_NOT_RUNTIME",
        "rule": {
            "strong_min_points": args.strong_min_points,
            "min_extent_y_m": args.min_extent_y_m,
            "max_extent_z_m": args.max_extent_z_m,
            "max_extent_x_m": args.max_extent_x_m,
            "min_abs_centroid_x_m": args.min_abs_centroid_x_m,
            "min_s_span_m": args.min_s_span_m,
            "min_y_to_x_ratio": args.min_y_to_x_ratio,
            "min_y_to_z_ratio": args.min_y_to_z_ratio,
        },
        "old_negative_sources": {
            "sources": old_rows,
            "totals": old_totals,
        },
        "cloud_with_fake_obj": {
            "geometry_frames_before": len(cloud_before),
            "geometry_frames_after": len(cloud_after),
            "removed_frames": sorted(cloud_before - cloud_after),
            "removed_examples": cloud_removed[:20],
            "event_eval_before": cloud_eval_before,
            "event_eval_after": cloud_eval_after,
        },
        "doubleT_obstacle": {
            "geometry_frames_before": len(doublet_before),
            "geometry_frames_after": len(doublet_after),
            "removed_frames": sorted(doublet_before - doublet_after),
            "removed_examples": doublet_removed[:20],
            "frame_eval_before": doublet_eval_before,
            "frame_eval_after": doublet_eval_after,
        },
        "decision_hint": {
            "removes_roundT_pressureGate_fp": any(
                row["source"] == "roundT_pressureGate_roundT" and row["geometry_fp_removed"] >= 3
                for row in old_rows
            ),
            "cloud_positive_events_preserved": (
                cloud_eval_after["positive_target_events_hit"]
                == cloud_eval_before["positive_target_events_hit"]
            ),
            "doublet_positive_frames_preserved": (
                doublet_eval_before["positive_frames_hit"] == doublet_eval_before["positive_frames_total"]
                and
                doublet_eval_after["positive_frames_hit"]
                == doublet_eval_before["positive_frames_hit"]
            ),
            "screening_verdict": "UNSET",
        },
        "limitations": [
            "This screens saved geometry artifacts only; it is not a C++/ROS2 change.",
            "It does not prove generalization beyond these development/screening inputs.",
            "UNKNOWN remains separate and is never treated as CLEAR.",
        ],
    }
    hint = payload["decision_hint"]
    hint["screening_verdict"] = (
        "REJECTED_BREAKS_POSITIVE_EVIDENCE"
        if not hint["cloud_positive_events_preserved"] or not hint["doublet_positive_frames_preserved"]
        else "PASS_OFFLINE_SCREENING_ONLY"
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "long_low_infrastructure_suppressor_screen.json", payload)
    print(
        json.dumps(
            {
                "output": str(args.output_dir),
                "old_negative_totals": old_totals,
                "cloud_after": cloud_eval_after,
                "doublet_after": doublet_eval_after,
                "decision_hint": payload["decision_hint"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
