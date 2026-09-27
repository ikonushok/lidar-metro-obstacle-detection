"""Screen simple geometry-first detector candidates over saved CORE components.

This is an offline development helper. It consumes component rows created by
``audit_geometric_core_cloud.py`` and writes frame-level detector flags that can
be evaluated by ``evaluate_working_obstacle_labels.py``. It does not change ROS2
runtime behavior and does not make a safety CLEAR decision.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rounded(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def component_is_boundary_warning(row: dict[str, Any]) -> bool:
    """Approximate known outside/above boundary shapes seen in cloud objects #7/#8."""
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


def component_is_high_support_obstacle(row: dict[str, Any], min_points: int) -> bool:
    return int(row.get("point_count", 0)) >= min_points


def component_is_compact_or_low_long(row: dict[str, Any], min_points: int) -> bool:
    """Hybrid geometry hook for compact blocks and rail-long low components."""
    if int(row.get("point_count", 0)) < min_points:
        return False
    extent = row.get("extent_xyz_m") or [0.0, 0.0, 0.0]
    ex, ey, ez = (float(extent[0]), float(extent[1]), float(extent[2]))
    compact_block = ex >= 0.25 and ez >= 0.20 and ey <= 1.00
    low_long = ez <= 0.35 and ey >= 2.00
    tall_block_with_overlap = ez >= 1.50 and ex >= 0.30
    return compact_block or low_long or tall_block_with_overlap


def component_brief(row: dict[str, Any]) -> dict[str, Any]:
    centroid = row.get("centroid_xyz") or [None, None, None]
    extent = row.get("extent_xyz_m") or [None, None, None]
    return {
        "frame": int(row["frame"]),
        "zone": row.get("zone", "core"),
        "point_count": int(row["point_count"]),
        "min_s_m": rounded(row.get("min_s_m")),
        "max_s_m": rounded(row.get("max_s_m")),
        "nearest_distance_m": rounded(row.get("nearest_distance_m")),
        "centroid_xyz": [rounded(value) for value in centroid],
        "extent_xyz_m": [rounded(value) for value in extent],
        "boundary_warning": component_is_boundary_warning(row),
    }


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


def build_frames(components: list[dict[str, Any]], min_points: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in components:
        if row.get("zone", "core") == "core":
            by_frame[int(row["frame"])].append(row)
    max_frame = max(by_frame, default=-1)
    suffix = f"ge{min_points}"
    raw_field = f"raw_core_{suffix}"
    boundary_field = f"geometry_boundary_warning_{suffix}"
    obstacle_field = f"geometry_boundary_suppressed_obstacle_{suffix}"
    hybrid_field = f"geometry_hybrid_obstacle_{suffix}"
    rows = []
    rule_frames: dict[str, set[int]] = {
        raw_field: set(),
        boundary_field: set(),
        obstacle_field: set(),
        hybrid_field: set(),
    }
    reason_counts: Counter[str] = Counter()
    for frame in range(max_frame + 1):
        frame_components = by_frame.get(frame, [])
        high_support = [
            row for row in frame_components
            if component_is_high_support_obstacle(row, min_points)
        ]
        boundary = [
            row for row in high_support
            if component_is_boundary_warning(row)
        ]
        high_obstacle = [
            row for row in high_support
            if not component_is_boundary_warning(row)
        ]
        hybrid_obstacle = [
            row for row in high_support
            if component_is_compact_or_low_long(row, min_points)
            and not component_is_boundary_warning(row)
        ]
        if high_support:
            rule_frames[raw_field].add(frame)
        if boundary:
            rule_frames[boundary_field].add(frame)
        if high_obstacle:
            rule_frames[obstacle_field].add(frame)
        if hybrid_obstacle:
            rule_frames[hybrid_field].add(frame)

        if high_obstacle:
            reason = "HIGH_SUPPORT_CORE_COMPONENT_NOT_BOUNDARY_WARNING"
        elif hybrid_obstacle:
            reason = "HYBRID_GEOMETRY_COMPONENT"
        elif boundary:
            reason = "BOUNDARY_WARNING"
        elif high_support:
            reason = "HIGH_SUPPORT_COMPONENT_SUPPRESSED"
        else:
            reason = "NO_HIGH_SUPPORT_COMPONENT"
        reason_counts[reason] += 1
        strongest = sorted(frame_components, key=lambda row: int(row["point_count"]), reverse=True)[:5]
        rows.append(
            {
                "index": frame,
                raw_field: bool(high_support),
                boundary_field: bool(boundary),
                obstacle_field: bool(high_obstacle),
                hybrid_field: bool(hybrid_obstacle),
                "geometry_reason": reason,
                "component_count": len(frame_components),
                "high_support_component_count": len(high_support),
                "boundary_warning_component_count": len(boundary),
                "obstacle_component_count": len(high_obstacle),
                "hybrid_obstacle_component_count": len(hybrid_obstacle),
                "largest_component": component_brief(strongest[0]) if strongest else None,
                "top_components": [component_brief(row) for row in strongest],
            }
        )
    summary = {
        "format": "geometry_first_candidate_screening_v1",
        "scope": "OFFLINE_COMPONENT_SCREENING_NOT_RUNTIME_OR_SAFETY_DECISION",
        "min_points": min_points,
        "frame_count": len(rows),
        "rules": {
            raw_field: f"any core component with point_count >= {min_points}",
            boundary_field: (
                "high-support boundary component: outside-left thin/tall or "
                "upper/above broad; warning/boundary, not obstacle"
            ),
            obstacle_field: (
                f"{raw_field} excluding {boundary_field} components"
            ),
            hybrid_field: (
                f"{raw_field} excluding boundary warning and requiring compact block, "
                "low-long, or tall block with wider core overlap"
            ),
        },
        "reason_counts": dict(reason_counts),
        "alarm_frames": {
            name: {
                "count": len(frames),
                "runs": summarize_runs(sorted(frames)),
            }
            for name, frames in rule_frames.items()
        },
        "limitations": [
            "Thresholds are development-screening rules over saved CORE components.",
            "A negative candidate flag does not mean CLEAR; UNKNOWN remains UNKNOWN.",
            "cloud_with_fake_obj is a development benchmark after organizer disclosure, not independent held-out.",
        ],
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-points", type=int, default=1000)
    args = parser.parse_args()
    if args.min_points < 1:
        raise ValueError("--min-points must be positive")
    components = load_json(args.components)
    if not isinstance(components, list):
        raise ValueError("--components must point to a JSON list")
    frames, summary = build_frames(components, args.min_points)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "frames.json").write_text(
        json.dumps(frames, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "frame_count": len(frames)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
