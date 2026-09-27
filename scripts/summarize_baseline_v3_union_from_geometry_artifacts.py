"""Summarize baseline_v3 union from saved geometry audit artifacts.

This helper is intentionally offline-only. It reconstructs the frozen
model_v1 per-frame temporal alarms from already extracted CORE component
summaries and unions them with the geometry-first gate output.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from typing import Any


MODEL_FEATURES = (
    "point_count",
    "extent_x_m",
    "extent_y_m",
    "extent_z_m",
    "volume_m3",
    "density_points_per_m3",
    "centroid_distance_m",
    "nearest_distance_m",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def component_features(row: dict[str, Any]) -> list[float]:
    extent = [float(value) for value in row.get("extent_xyz_m", [0.0, 0.0, 0.0])]
    centroid = [float(value) for value in row.get("centroid_xyz", [0.0, 0.0, 0.0])]
    volume = max(extent[0] * extent[1] * extent[2], 1e-6)
    point_count = float(row.get("point_count", 0))
    return [
        point_count,
        extent[0],
        extent[1],
        extent[2],
        volume,
        point_count / volume,
        math.sqrt(sum(axis * axis for axis in centroid)),
        float(row.get("nearest_distance_m") or 0.0),
    ]


def predict_probability(tree: dict[str, Any], values: list[float]) -> float:
    positions = {name: index for index, name in enumerate(MODEL_FEATURES)}
    node = tree
    while "feature" in node:
        node = node["left"] if values[positions[node["feature"]]] <= node["threshold"] else node["right"]
    total = float(node["positive_weight"]) + float(node["negative_weight"])
    return 0.0 if total <= 0.0 else float(node["positive_weight"]) / total


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


def source_ids(root: Path) -> list[str]:
    return sorted(path.name for path in (root / "raw_core_60m").iterdir() if path.is_dir())


def model_raw_alarm_frames(components: list[dict[str, Any]], tree: dict[str, Any], threshold: float) -> set[int]:
    frames = set()
    for row in components:
        if row.get("zone", "core") != "core":
            continue
        if predict_probability(tree, component_features(row)) >= threshold:
            frames.add(int(row["frame"]))
    return frames


def apply_causal_temporal(frame_count: int, unknown: set[int], raw_alarm: set[int]) -> set[int]:
    temporal = set()
    previous_alarm = False
    consecutive_alarm_frames = 0
    for frame in range(frame_count):
        if frame in unknown:
            previous_alarm = False
            consecutive_alarm_frames = 0
            continue
        alarm = frame in raw_alarm
        consecutive_alarm_frames = consecutive_alarm_frames + 1 if previous_alarm and alarm else (1 if alarm else 0)
        if alarm and consecutive_alarm_frames >= 2:
            temporal.add(frame)
        previous_alarm = alarm
    return temporal


def summarize_source(root: Path, source_id: str, tree: dict[str, Any], threshold: float,
                     historical: dict[str, dict[str, int]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_dir = root / "raw_core_60m" / source_id
    gate_dir = root / "gate_ml_apply" / source_id
    raw_summary = load_json(raw_dir / "summary.json")
    raw_frames = load_json(raw_dir / "frames.json")
    components = load_json(raw_dir / "components.json")
    gate_frames = load_json(gate_dir / "frames.json")

    frame_count = int(raw_summary["frame_count"])
    unknown = {int(row["frame"]) for row in raw_frames if row.get("status") == "UNKNOWN"}
    geometry = {
        int(row["index"])
        for row in gate_frames
        if bool(row.get("geometry_gate_ml_suppressor_obstacle"))
    }
    raw_alarm = model_raw_alarm_frames(components, tree, threshold)
    temporal = apply_causal_temporal(frame_count, unknown, raw_alarm)
    union = {frame for frame in geometry | temporal if frame not in unknown}
    non_unknown = frame_count - len(unknown)

    hist = historical.get(source_id, {})
    summary = {
        "source": source_id,
        "frames": frame_count,
        "unknown": len(unknown),
        "geometry_fp": len(geometry - unknown),
        "model_v1_temporal_fp": len(temporal - unknown),
        "baseline_v3_fp_union": len(union),
        "baseline_v3_tn": non_unknown - len(union),
        "geometry_model_overlap": len((geometry & temporal) - unknown),
        "old_temporal_fp": hist.get("old_temporal_fp"),
        "old_unknown": hist.get("old_unknown"),
        "delta_fp_vs_old_temporal": (
            len(union) - int(hist["old_temporal_fp"])
            if "old_temporal_fp" in hist else None
        ),
        "delta_unknown_vs_old": (
            len(unknown) - int(hist["old_unknown"])
            if "old_unknown" in hist else None
        ),
        "raw_model_alarm_frames": len(raw_alarm - unknown),
        "baseline_v3_fp_runs": summarize_runs(sorted(union))[:40],
    }
    frame_rows = [
        {
            "source": source_id,
            "frame": frame,
            "unknown": frame in unknown,
            "geometry_obstacle": frame in geometry,
            "model_v1_raw_alarm": frame in raw_alarm,
            "model_v1_temporal_alarm": frame in temporal,
            "baseline_v3_obstacle": frame in union,
        }
        for frame in range(frame_count)
    ]
    return summary, frame_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=Path("models/noise_classifier_doubleT_obstacle_v1.json"))
    parser.add_argument("--historical-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    model = load_json(args.model)
    tree = model["tree"]
    historical = {}
    if args.historical_summary is not None:
        for row in load_json(args.historical_summary).get("sources", []):
            historical[row["source"]] = row

    sources = []
    frames = []
    for source_id in source_ids(args.root):
        source_summary, source_frames = summarize_source(
            args.root, source_id, tree, args.threshold, historical
        )
        sources.append(source_summary)
        frames.extend(source_frames)

    totals = {
        "frames": sum(row["frames"] for row in sources),
        "unknown": sum(row["unknown"] for row in sources),
        "geometry_fp": sum(row["geometry_fp"] for row in sources),
        "model_v1_temporal_fp": sum(row["model_v1_temporal_fp"] for row in sources),
        "baseline_v3_fp_union": sum(row["baseline_v3_fp_union"] for row in sources),
        "baseline_v3_tn": sum(row["baseline_v3_tn"] for row in sources),
        "geometry_model_overlap": sum(row["geometry_model_overlap"] for row in sources),
        "old_temporal_fp": sum(int(row["old_temporal_fp"] or 0) for row in sources),
        "old_unknown": sum(int(row["old_unknown"] or 0) for row in sources),
    }
    totals["delta_fp_vs_old_temporal"] = totals["baseline_v3_fp_union"] - totals["old_temporal_fp"]
    totals["delta_unknown_vs_old"] = totals["unknown"] - totals["old_unknown"]

    payload = {
        "format": "baseline_v3_union_old_negative_sources_v1",
        "scope": "OFFLINE_UNION_FROM_SAVED_GEOMETRY_ARTIFACTS_NOT_RUNTIME",
        "model": str(args.model),
        "threshold": args.threshold,
        "temporal_rule": "causal consecutive alarm frames >= 2; UNKNOWN resets state and is not CLEAR",
        "metric_rule": "Old negative sources: every baseline_v3_obstacle on a non-UNKNOWN frame is FP; UNKNOWN is counted separately.",
        "sources": sources,
        "totals": totals,
        "status_counts": dict(Counter("UNKNOWN" if row["unknown"] else "EVALUATED" for row in frames)),
        "limitations": [
            "Uses component summaries saved by audit_geometric_core_cloud.py, not a fresh C++ replay.",
            "Components below 22 points are absent from the audit artifact; model_v1 tree cannot alarm below 105 points, so this does not affect current tree positives.",
            "Old_temporal_fp/old_unknown are historical comparator numbers; baseline_v3 union is computed on the current geometry audit artifacts.",
        ],
    }
    write_json(args.output / "baseline_v3_union_old_negative_summary.json", payload)
    write_json(args.output / "baseline_v3_union_old_negative_frames.json", frames)
    print(json.dumps({"output": str(args.output), "totals": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
