"""Localize remaining cloud_with_fake_obj synthetic-object windows from raw CORE components.

This is an offline evidence helper. It does not define runtime detector
behavior and does not treat boundary/above-gabarit objects as target obstacles.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
from typing import Any


TARGET_SOURCE = "cloud_with_fake_obj"
UNKNOWN_ORDERS = {5, 8, 10}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_runs(frames: list[int]) -> list[dict[str, int]]:
    if not frames:
        return []
    runs = []
    start = prev = frames[0]
    for frame in frames[1:]:
        if frame == prev + 1:
            prev = frame
            continue
        runs.append({"start": start, "end": prev, "count": prev - start + 1})
        start = prev = frame
    runs.append({"start": start, "end": prev, "count": prev - start + 1})
    return runs


def event_interval(event: dict[str, Any]) -> tuple[int, int] | None:
    value = event.get("frame_interval")
    if value is None:
        return None
    return int(value[0]), int(value[1])


def source_events(labels: dict[str, Any]) -> list[dict[str, Any]]:
    for source in labels.get("sources", []):
        if source.get("source_id") == TARGET_SOURCE:
            return list(source.get("events", []))
    raise KeyError(f"{TARGET_SOURCE} missing from labels")


def search_ranges(events: list[dict[str, Any]], max_frame: int) -> dict[int, tuple[int, int]]:
    by_order = {int(event["organizer_order"]): event for event in events if event.get("organizer_order")}
    ranges = {}
    for order in UNKNOWN_ORDERS:
        prev_end = 0
        next_start = max_frame
        for previous in range(order - 1, 0, -1):
            interval = event_interval(by_order[previous])
            if interval is not None:
                prev_end = interval[1] + 1
                break
        for following in range(order + 1, 99):
            if following not in by_order:
                break
            interval = event_interval(by_order[following])
            if interval is not None:
                next_start = interval[0] - 1
                break
        ranges[order] = (prev_end, next_start)
    return ranges


def component_kind(row: dict[str, Any]) -> str:
    centroid = row["centroid_xyz"]
    extent = row["extent_xyz_m"]
    point_count = int(row["point_count"])
    if centroid[0] < -1.30 and extent[0] < 0.25 and extent[2] > 1.50:
        return "outside_left_thin_tall_boundary"
    if centroid[2] > 0.35 and extent[2] > 0.30:
        return "upper_component_candidate"
    if extent[2] < 0.08 and extent[1] > 1.0:
        return "rail_floor_line_like"
    if point_count >= 1000:
        return "high_support_core_candidate"
    if extent[2] >= 0.18 and point_count >= 150:
        return "compact_or_vertical_candidate"
    return "sparse_background_candidate"


def is_candidate(row: dict[str, Any], order: int) -> bool:
    point_count = int(row["point_count"])
    extent = row["extent_xyz_m"]
    centroid = row["centroid_xyz"]
    kind = component_kind(row)
    if order == 5:
        return (
            point_count >= 150
            and extent[2] >= 0.12
            and extent[2] <= 0.65
            and extent[0] <= 0.60
            and extent[1] <= 1.25
            and abs(centroid[0]) >= 1.0
        )
    if order == 8:
        return (
            point_count >= 180
            and (
                kind == "outside_left_thin_tall_boundary"
                or kind == "upper_component_candidate"
                or (extent[2] >= 0.80 and abs(centroid[0]) >= 0.9)
            )
        )
    if order == 10:
        return (
            point_count >= 80
            and extent[2] >= 0.25
            and extent[0] <= 0.16
            and extent[1] <= 1.50
        )
    return False


def representative(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame": int(row["frame"]),
        "point_count": int(row["point_count"]),
        "min_s_m": row.get("min_s_m"),
        "max_s_m": row.get("max_s_m"),
        "nearest_distance_m": row.get("nearest_distance_m"),
        "centroid_xyz": row.get("centroid_xyz"),
        "extent_xyz_m": row.get("extent_xyz_m"),
        "component_kind": component_kind(row),
    }


def summarize_candidate_run(frames: list[int], by_frame: dict[int, list[dict[str, Any]]], order: int) -> dict[str, Any]:
    candidate_rows = []
    for frame in frames:
        candidate_rows.extend(row for row in by_frame[frame] if is_candidate(row, order))
    best = max(candidate_rows, key=lambda row: int(row["point_count"]))
    return {
        "start": frames[0],
        "end": frames[-1],
        "count": len(frames),
        "best_component": representative(best),
        "top_components": [
            representative(row)
            for row in sorted(candidate_rows, key=lambda item: int(item["point_count"]), reverse=True)[:8]
        ],
    }


def localize(
    components: list[dict[str, Any]],
    labels: dict[str, Any],
) -> dict[str, Any]:
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in components:
        by_frame[int(row["frame"])].append(row)
    max_frame = max(by_frame, default=0)
    events = source_events(labels)
    ranges = search_ranges(events, max_frame)
    object_rows = []
    for order, (first, last) in sorted(ranges.items()):
        candidate_frames = [
            frame for frame in range(first, last + 1)
            if any(is_candidate(row, order) for row in by_frame.get(frame, []))
        ]
        run_summaries = [
            summarize_candidate_run(list(range(run["start"], run["end"] + 1)), by_frame, order)
            for run in summarize_runs(candidate_frames)
        ]
        object_rows.append({
            "organizer_order": order,
            "search_range": [first, last],
            "candidate_frame_count": len(candidate_frames),
            "candidate_runs": run_summaries,
        })
    return {
        "format": "cloud_synthetic_object_localization_v1",
        "scope": "OFFLINE_LOCALIZATION_EVIDENCE_NOT_RUNTIME_DECISION",
        "source_id": TARGET_SOURCE,
        "method": (
            "Search only unlabeled organizer-order gaps. Candidate frames come from raw CORE "
            "component geometry; outside/above objects remain negative_boundary unless their "
            "points are shown to intersect the accepted core-gabarit."
        ),
        "objects": object_rows,
    }


def update_labels(labels: dict[str, Any], localization: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(labels)
    intervals_by_order: dict[int, list[int] | None] = {
        5: None,
        8: None,
        10: None,
    }
    notes_by_order: dict[int, str] = {
        5: "No stable raw CORE component localized in the order gap; remains boundary/negative but unscorable.",
        8: "No stable above-gabarit CORE component localized in the order gap; remains boundary/negative but unscorable.",
        10: "No narrow hanging CORE-intersection localized; positive claim remains unscorable.",
    }
    # Conservative: #8 gets a tentative window only for the clear upper/above
    # component run. #5/#10 stay null unless the raw CORE evidence matches their
    # expected geometry instead of a neighbouring object's ramp-up.
    for row in localization["objects"]:
        order = int(row["organizer_order"])
        runs = row["candidate_runs"]
        if order == 8 and runs:
            upper_runs = [
                run for run in runs
                if run["best_component"]["component_kind"] == "upper_component_candidate"
            ]
            if upper_runs:
                best = max(upper_runs, key=lambda item: item["best_component"]["point_count"])
                intervals_by_order[8] = [best["start"], best["end"]]
                notes_by_order[8] = (
                    "Tentative above-gabarit raw CORE localization; negative_boundary for "
                    "obstacle scoring, not target obstacle."
                )
    for source in updated.get("sources", []):
        if source.get("source_id") != TARGET_SOURCE:
            continue
        for event in source.get("events", []):
            order = event.get("organizer_order")
            if order not in intervals_by_order:
                continue
            if intervals_by_order[order] is not None:
                event["frame_interval"] = intervals_by_order[order]
                event["matching_status"] = "tentative_raw_core_localization"
                event["label_source"] = "organizer_description_plus_raw_core_gap_search"
            event["notes"] = notes_by_order[order]
    updated["format"] = "lidar_obstacle_working_event_labels_v1_localization_probe"
    updated["scope"] = "development_benchmark_not_final_gt_localization_probe"
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    components = load_json(args.components)
    labels = load_json(args.labels)
    localization = localize(components, labels)
    updated_labels = update_labels(labels, localization)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "localization_summary.json").write_text(
        json.dumps(localization, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "cloud_with_fake_obj_localization_probe_labels.json").write_text(
        json.dumps(updated_labels, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
