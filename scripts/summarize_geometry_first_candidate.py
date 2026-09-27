"""Summarize geometry-first screening artifacts for stage 5 reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EVENT_WINDOWS = {
    "cloud_fake_obj_01_2x2_center": (204, 216, "positive_target"),
    "cloud_fake_obj_02_small_center": (365, 368, "positive_target"),
    "cloud_fake_obj_03_small_on_rails": (478, 480, "positive_target"),
    "cloud_fake_obj_04_small_edge_inside": (530, 532, "positive_target"),
    "cloud_fake_obj_06_2x2_edge_inside": (579, 581, "positive_target"),
    "cloud_fake_obj_07_2x2_outside": (630, 633, "negative_boundary"),
    "cloud_fake_obj_09_long_low_on_rails": (1138, 1156, "positive_target"),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, list):
        return [round_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: round_floats(item) for key, item in value.items()}
    return value


def component_brief(row: dict[str, Any]) -> dict[str, Any]:
    return round_floats(
        {
            "frame": row["frame"],
            "point_count": row["point_count"],
            "min_s_m": row.get("min_s_m"),
            "max_s_m": row.get("max_s_m"),
            "nearest_distance_m": row.get("nearest_distance_m"),
            "centroid_xyz": row.get("centroid_xyz"),
            "extent_xyz_m": row.get("extent_xyz_m"),
        }
    )


def feature_comparison(components: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for event_id, (first, last, expected_class) in EVENT_WINDOWS.items():
        event_components = [
            row for row in components
            if first <= int(row["frame"]) <= last and row.get("zone", "core") == "core"
        ]
        top = sorted(event_components, key=lambda row: int(row["point_count"]), reverse=True)[:8]
        rows.append(
            {
                "event_id": event_id,
                "expected_class": expected_class,
                "frame_interval": [first, last],
                "component_count": len(event_components),
                "top_components": [component_brief(row) for row in top],
            }
        )
    return {
        "format": "geometry_first_feature_comparison_v1",
        "component_source": "raw CORE audit components.json",
        "events": rows,
    }


def detector_summary(eval_path: Path) -> dict[str, Any]:
    data = load_json(eval_path)
    return {
        "source_id": data["source_id"],
        "eval_path": str(eval_path),
        "detectors": {
            name: {
                "positive_target_events_hit": result["positive_target_events_hit"],
                "positive_target_events_scorable": result["positive_target_events_scorable"],
                "positive_target_events_missed": result["positive_target_events_missed"],
                "negative_boundary_false_positive_events": result[
                    "negative_boundary_false_positive_events"
                ],
                "negative_boundary_events_scorable": result["negative_boundary_events_scorable"],
                "alarm_frame_count": result["alarm_frame_count"],
                "unassigned_alarm_frame_count": result["unassigned_alarm_frame_count"],
                "alarm_runs": result["alarm_runs"],
            }
            for name, result in data["detectors"].items()
            if not name.startswith(("causal_", "frame_model_"))
        },
    }


def doublet_frame_regression(frames_path: Path, fields: list[str]) -> dict[str, Any]:
    rows = load_json(frames_path)
    positive_window = range(13, 65)
    results = {}
    for field in fields:
        positive_hits = [
            int(row["index"]) for row in rows
            if int(row["index"]) in positive_window and bool(row.get(field))
        ]
        outside_alarms = [
            int(row["index"]) for row in rows
            if int(row["index"]) not in positive_window and bool(row.get(field))
        ]
        missing = [frame for frame in positive_window if frame not in set(positive_hits)]
        results[field] = {
            "positive_frames_hit": len(positive_hits),
            "positive_frames_total": 52,
            "missing_positive_frames": missing,
            "outside_alarm_frames": len(outside_alarms),
            "outside_alarm_frame_examples": outside_alarms[:50],
        }
    return {
        "format": "doubleT_obstacle_frame_regression_v1",
        "source": str(frames_path),
        "positive_window_inclusive": [13, 64],
        "detectors": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud-components", type=Path, required=True)
    parser.add_argument("--cloud-ge1000-eval", type=Path, required=True)
    parser.add_argument("--cloud-ge250-eval", type=Path, required=True)
    parser.add_argument("--doublet-ge1000-eval", type=Path, required=True)
    parser.add_argument("--doublet-ge250-eval", type=Path, required=True)
    parser.add_argument("--doublet-ge1000-frames", type=Path, required=True)
    parser.add_argument("--doublet-ge250-frames", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    comparison = feature_comparison(load_json(args.cloud_components))
    (args.output / "cloud_feature_comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metric_summary = {
        "format": "geometry_first_metric_summary_v1",
        "cloud_ge1000": detector_summary(args.cloud_ge1000_eval),
        "cloud_ge250": detector_summary(args.cloud_ge250_eval),
        "doubleT_ge1000": detector_summary(args.doublet_ge1000_eval),
        "doubleT_ge250": detector_summary(args.doublet_ge250_eval),
        "limitations": [
            "Event-level evaluator only checks localized windows.",
            "doubleT frame regression is a separate 13..64 frame count.",
            "No result is a runtime safety decision.",
        ],
    }
    (args.output / "metric_summary.json").write_text(
        json.dumps(metric_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    doublet_summary = {
        "ge1000": doublet_frame_regression(
            args.doublet_ge1000_frames,
            [
                "raw_core_ge1000",
                "geometry_boundary_suppressed_obstacle_ge1000",
                "geometry_hybrid_obstacle_ge1000",
            ],
        ),
        "ge250": doublet_frame_regression(
            args.doublet_ge250_frames,
            [
                "raw_core_ge250",
                "geometry_boundary_suppressed_obstacle_ge250",
                "geometry_hybrid_obstacle_ge250",
            ],
        ),
    }
    (args.output / "doubleT_frame_regression.json").write_text(
        json.dumps(doublet_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
