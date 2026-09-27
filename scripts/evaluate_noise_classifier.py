"""Compare the existing C++ component filter with the frozen offline tree on all sources.

This diagnostic evaluator never changes a runtime decision.  A model-negative
component does not establish that the track is clear.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import time

from archive_bag_frames import ArchiveBagFrames
from train_noise_classifier import connected_components, component_features, predict_probability


SOURCES = (
    ("roundT_doubleT", "for_hackathon/roundT_doubleT", "for_hackathon"),
    ("squareT_platform_squareT_switch", "for_hackathon/squareT_platform_squareT_switch", "for_hackathon"),
    ("doubleT_platform", "for_hackathon/doubleT_platform", "for_hackathon"),
    ("roundT_squareT_pressureGate_squareT", "for_hackathon/roundT_squareT_pressureGate_squareT", "for_hackathon"),
    ("doubleT_obstacle", "for_hackathon/doubleT_obstacle", "for_hackathon"),
    ("roundT_pressureGate_roundT", "for_hackathon/roundT_pressureGate_roundT", "for_hackathon"),
    ("new_data", "new_data", "new_data"),
)

UNKNOWN_REASON_DESCRIPTIONS_RU = {
    "AMBIGUOUS_LOCAL_CONTINUITY_PATH": "неоднозначная непрерывная цепочка рельсовой оси",
    "INSUFFICIENT_CONTIGUOUS_COVERAGE": "недостаточное непрерывное покрытие опорных сечений",
    "INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT": "недостаточно локально непрерывных пар рельсов",
    "MISSING_CURVE_AXIS": "не удалось построить криволинейную ось рельсов",
    "NO_RETURNS_INTERSECT_REFERENCE_NOT_CLEAR": "нет возвратов в reference-габарите, но это не доказанный CLEAR",
}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[math.ceil(len(values) * fraction) - 1]


def analyze_frame(raw: bytes, result: dict, tree: dict, frame: int, is_positive_source: bool) -> dict:
    if result["status"] == "UNKNOWN":
        return {
            "unknown": True,
            "target": is_positive_source and 13 <= frame <= 64,
            "unknown_reason": result.get("reason", "<missing>"),
            "curve_axis_status": result.get("curve_axis_status", "<missing>"),
            "rail_axis_failure_diagnostics": result.get("rail_axis_failure_diagnostics"),
        }
    expected = {"min_reportable_core_points": 22, "connectivity_radius_m": 0.25,
                "max_axis_span_m": 1.0, "max_average_axis_distance_m": 1.2}
    if result.get("noise_filter_config") != expected:
        raise ValueError(f"frame {frame}: C++ filter config mismatch")
    started = time.perf_counter_ns()
    groups = connected_components(raw, result["core_source_indices"], 0.25)
    reportable = set(result["reportable_core_source_indices"])
    legacy_groups = [group for group in groups if set(group) <= reportable]
    if set().union(*(set(group) for group in legacy_groups)) != reportable:
        raise ValueError(f"frame {frame}: Python groups disagree with C++ reportable indices")
    target_group = max(legacy_groups, key=len) if is_positive_source and 13 <= frame <= 64 and legacy_groups else None
    if "model_reportable_core_source_indices" in result:
        model_reportable = set(result["model_reportable_core_source_indices"])
        model_groups = [group for group in groups if set(group) <= model_reportable]
        if set().union(*(set(group) for group in model_groups)) != model_reportable:
            raise ValueError(f"frame {frame}: Python groups disagree with C++ model indices")
        python_model_groups = [group for group in groups if predict_probability(tree, component_features(raw, group)) >= 0.5]
        if {tuple(group) for group in model_groups} != {tuple(group) for group in python_model_groups}:
            raise ValueError(f"frame {frame}: C++ model disagrees with frozen Python tree")
    else:
        model_groups = [group for group in groups if predict_probability(tree, component_features(raw, group)) >= 0.5]
    elapsed_ms = (time.perf_counter_ns() - started) / 1e6
    target_id = id(target_group) if target_group is not None else None
    return {
        "unknown": False, "target": is_positive_source and 13 <= frame <= 64,
        "target_available": target_group is not None,
        "legacy_alarm": bool(legacy_groups), "model_alarm": bool(model_groups),
        "legacy_target_hit": target_id is not None and any(id(group) == target_id for group in legacy_groups),
        "model_target_hit": target_id is not None and any(id(group) == target_id for group in model_groups),
        "legacy_false_components": len(legacy_groups) - int(target_id is not None),
        "model_false_components": sum(id(group) != target_id for group in model_groups),
        "legacy_component_count": len(legacy_groups), "model_component_count": len(model_groups),
        "core_component_count": len(groups), "postprocess_ms": elapsed_ms,
        "cpp_processing_ms": result.get("legacy_processing_ms", result.get("processing_ms")),
        "cpp_model_processing_ms": result.get("model_processing_ms"),
        "cpp_common_processing_ms": result.get("common_processing_ms"),
        "cpp_legacy_noise_filter_ms": result.get("legacy_noise_filter_ms"),
        "cpp_model_noise_filter_ms": result.get("model_noise_filter_ms"),
    }


def apply_model_temporal_confirmation(rows: list[dict]) -> None:
    """Mirror the current runtime consecutive-frame temporal confirmation."""
    previous_alarm = False
    consecutive_alarm_frames = 0
    for row in rows:
        if row["unknown"]:
            previous_alarm = False
            consecutive_alarm_frames = 0
        elif row.get("model_alarm"):
            consecutive_alarm_frames = consecutive_alarm_frames + 1 if previous_alarm else 1
        else:
            consecutive_alarm_frames = 0
        confirmed = (
            not row["unknown"] and row.get("model_alarm") and consecutive_alarm_frames >= 2
        )
        row["model_temporal_alarm"] = confirmed
        row["model_temporal_target_hit"] = confirmed and row.get("model_target_hit", False)
        row["model_temporal_false_components"] = row.get("model_false_components", 0) if confirmed else 0
        row["model_temporal_component_count"] = row.get("model_component_count", 0) if confirmed else 0
        previous_alarm = not row["unknown"] and bool(row.get("model_alarm"))


def evaluate_source(root: Path, output: Path, source_id: str, prefix: str, archive_name: str,
                    tree: dict, stream_cli: str, first: int, last: int | None,
                    duration_seconds: float | None) -> dict:
    archive = root / "dataset/for_hackathon" / archive_name
    source = ArchiveBagFrames(archive, prefix, source_id)
    process = subprocess.Popen([stream_cli, "2.0", "--compare-noise-filters"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rows = []
    try:
        final = len(source.lookup) - 1 if last is None else min(last, len(source.lookup) - 1)
        first_offset = None
        for frame in range(first, final + 1):
            record, raw = source.frame(frame)
            if first_offset is None:
                first_offset = record["bag_offset_seconds"]
            if duration_seconds is not None and rows and record["bag_offset_seconds"] - first_offset > duration_seconds:
                break
            process.stdin.write(struct.pack("<Q", len(raw) // 12))
            process.stdin.write(raw)
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                raise RuntimeError(f"{source_id} frame {frame}: C++ stream stopped: " +
                                   process.stderr.read().decode(errors="replace")[-1000:])
            result = json.loads(line)
            if result.get("safety_decision_permitted") is not False:
                raise ValueError(f"{source_id} frame {frame}: safety contract changed")
            if result.get("status") != "UNKNOWN" and result.get("rail_selection_method") != "development_candidate":
                raise ValueError(f"{source_id} frame {frame}: rail method mismatch")
            row = analyze_frame(raw, result, tree, frame, source_id == "doubleT_obstacle")
            row["frame"] = frame
            row["bag_offset_seconds"] = record["bag_offset_seconds"]
            rows.append(row)
            if frame % 100 == 0:
                print(f"{source_id}: {frame + 1}/{len(source.lookup)}", flush=True)
    finally:
        source.close()
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    apply_model_temporal_confirmation(rows)
    unknown_rows = [row for row in rows if row["unknown"]]
    unknown_reasons = sorted({row.get("unknown_reason", "<missing>") for row in unknown_rows})
    totals = {"frames": len(rows), "expected_frames": len(source.lookup),
              "unknown": sum(row["unknown"] for row in rows),
              "unknown_reason_counts": dict(Counter(row.get("unknown_reason", "<missing>")
                                                    for row in unknown_rows)),
              "unknown_reason_descriptions_ru": {
                  reason: UNKNOWN_REASON_DESCRIPTIONS_RU.get(reason, "нет русской расшифровки")
                  for reason in unknown_reasons
              },
              "unknown_curve_axis_status_counts": dict(Counter(row.get("curve_axis_status", "<missing>")
                                                               for row in unknown_rows)),
              "unknown_frame_keys_by_reason": {
                  reason: [row["frame"] for row in unknown_rows
                           if row.get("unknown_reason", "<missing>") == reason]
                  for reason in unknown_reasons
              },
              "positive_frames": sum(row["target"] for row in rows),
              "available_positive_frames": sum(row["target"] and not row["unknown"] for row in rows),
              "duration_seconds": (rows[-1]["bag_offset_seconds"] - rows[0]["bag_offset_seconds"])
              if len(rows) > 1 else 0.0}
    for method in ("legacy", "model", "model_temporal"):
        totals[method] = {
            "tp_frames": sum(row["target"] and not row["unknown"] and row[method + "_target_hit"] for row in rows),
            "fn_frames": sum(row["target"] and (row["unknown"] or not row[method + "_target_hit"]) for row in rows),
            "fp_frames": sum(not row["target"] and not row["unknown"] and row[method + "_alarm"] for row in rows),
            "tn_frames": sum(not row["target"] and not row["unknown"] and not row[method + "_alarm"] for row in rows),
            "fp_components": sum(row.get(method + "_false_components", 0) for row in rows),
            "alarm_frames": sum(not row["unknown"] and row[method + "_alarm"] for row in rows),
        }
        totals[method]["fp_frames_per_minute"] = (
            totals[method]["fp_frames"] * 60 / totals["duration_seconds"]
            if totals["duration_seconds"] > 0 else None)
    totals["cpp_processing_p95_ms"] = percentile([row["cpp_processing_ms"] for row in rows
                                                    if not row["unknown"] and row["cpp_processing_ms"] is not None], .95)
    totals["cpp_model_processing_p95_ms"] = percentile([row["cpp_model_processing_ms"] for row in rows
                                                        if not row["unknown"] and row["cpp_model_processing_ms"] is not None], .95)
    totals["cpp_legacy_noise_filter_p95_ms"] = percentile([row["cpp_legacy_noise_filter_ms"] for row in rows
                                                           if not row["unknown"] and row["cpp_legacy_noise_filter_ms"] is not None], .95)
    totals["cpp_model_noise_filter_p95_ms"] = percentile([row["cpp_model_noise_filter_ms"] for row in rows
                                                          if not row["unknown"] and row["cpp_model_noise_filter_ms"] is not None], .95)
    totals["model_postprocess_p95_ms"] = percentile([row["postprocess_ms"] for row in rows if not row["unknown"]], .95)
    totals["false_alarm_frame_examples"] = {
        method: [row["frame"] for row in rows if not row["target"] and not row["unknown"]
                 and row[method + "_alarm"]][:30] for method in ("legacy", "model", "model_temporal")}
    totals["model_temporal_config"] = {
        "scope": "FRAME_LEVEL_DIAGNOSTIC_POST_MODEL_FILTER",
        "rule": "current model_alarm and at least one adjacent non-UNKNOWN model_alarm",
        "window": "2-of-3 over previous/current/next frame",
    }
    totals["source_id"] = source_id
    totals["range_inclusive"] = [rows[0]["frame"], rows[-1]["frame"]] if rows else [first, final]
    path = output / f"{source_id}.json"
    path.write_text(json.dumps(totals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("DONE " + json.dumps({"source": source_id, "frames": totals["frames"],
                                "legacy_fp_frames": totals["legacy"]["fp_frames"],
                                "model_fp_frames": totals["model"]["fp_frames"],
                                "unknown": totals["unknown"]}, ensure_ascii=False), flush=True)
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stream-cli", default="/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    parser.add_argument("--source", choices=[item[0] for item in SOURCES])
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--last", type=int)
    parser.add_argument("--duration-seconds", type=float)
    args = parser.parse_args()
    if args.first < 0 or args.last is not None and args.last < args.first:
        raise ValueError("invalid frame range")
    if args.duration_seconds is not None and args.duration_seconds <= 0:
        raise ValueError("invalid duration")
    args.output.mkdir(parents=True, exist_ok=True)
    model = json.loads((args.root / "models/noise_classifier_doubleT_obstacle_v1.json").read_text(encoding="utf-8"))
    if model["format"] != "lidar-component-noise-tree-v1" or model["training"]["connectivity_radius_m"] != .25:
        raise ValueError("unexpected model contract")
    for source_id, prefix, archive_name in SOURCES:
        if args.source is not None and source_id != args.source:
            continue
        evaluate_source(args.root, args.output, source_id, prefix, archive_name,
                        model["tree"], args.stream_cli, args.first, args.last, args.duration_seconds)


if __name__ == "__main__":
    main()
