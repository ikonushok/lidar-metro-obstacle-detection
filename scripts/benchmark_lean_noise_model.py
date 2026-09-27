"""Run the lean C++ model benchmark on one source window.

The benchmark uses curve_pipeline_stream_cli --lean-model-benchmark and avoids
viewer/debug arrays.  It is meant for latency measurement, not for component
membership validation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import subprocess

from archive_bag_frames import ArchiveBagFrames


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[math.ceil(len(values) * fraction) - 1]


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def timing_stats(rows: list[dict], key: str) -> dict:
    values = [row[key] for row in rows if row.get(key) is not None]
    return {
        "mean_ms": mean(values),
        "p50_ms": percentile(values, .50),
        "p95_ms": percentile(values, .95),
        "max_ms": max(values) if values else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", default="new_data")
    parser.add_argument("--prefix", default="new_data")
    parser.add_argument("--archive-name", default="new_data")
    parser.add_argument("--duration-seconds", type=float, default=300.0)
    parser.add_argument("--stream-cli", default="/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    parser.add_argument("--profile-model-filter", action="store_true")
    args = parser.parse_args()
    if args.duration_seconds <= 0.0:
        raise ValueError("duration must be positive")

    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.root / "dataset/for_hackathon" / args.archive_name
    source = ArchiveBagFrames(archive, args.prefix, args.source)
    command = [args.stream_cli, "2.0", "--lean-model-benchmark"]
    if args.profile_model_filter:
        command.append("--profile-model-filter")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows: list[dict] = []
    try:
        first_offset = None
        for frame in range(len(source.lookup)):
            record, raw = source.frame(frame)
            if first_offset is None:
                first_offset = record["bag_offset_seconds"]
            if rows and record["bag_offset_seconds"] - first_offset > args.duration_seconds:
                break
            process.stdin.write(struct.pack("<Q", len(raw) // 12))
            process.stdin.write(raw)
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                raise RuntimeError(
                    f"{args.source} frame {frame}: C++ stream stopped: "
                    + process.stderr.read().decode(errors="replace")[-1000:]
                )
            result = json.loads(line)
            if result.get("format") != "lidar-curve-envelope-lean-benchmark-v1":
                raise ValueError(f"{args.source} frame {frame}: unexpected format")
            if result.get("safety_decision_permitted") is not False:
                raise ValueError(f"{args.source} frame {frame}: safety contract changed")
            result["frame"] = frame
            result["bag_offset_seconds"] = record["bag_offset_seconds"]
            rows.append(result)
            if frame % 100 == 0:
                print(f"{args.source}: {frame + 1}/{len(source.lookup)}", flush=True)
    finally:
        source.close()
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    supported = [row for row in rows if row["status"] != "UNKNOWN"]
    totals = {
        "source_id": args.source,
        "frames": len(rows),
        "expected_frames": len(source.lookup),
        "range_inclusive": [rows[0]["frame"], rows[-1]["frame"]] if rows else [0, -1],
        "duration_seconds": (
            rows[-1]["bag_offset_seconds"] - rows[0]["bag_offset_seconds"]
            if len(rows) > 1 else 0.0
        ),
        "unknown": sum(row["status"] == "UNKNOWN" for row in rows),
        "fp_frames": sum(row.get("obstacle_candidate_present") is True for row in supported),
        "tn_frames": sum(row.get("obstacle_candidate_present") is False for row in supported),
        "processing_p95_ms": percentile(
            [row["processing_ms"] for row in supported if row.get("processing_ms") is not None], .95
        ),
        "common_processing_p95_ms": percentile(
            [row["common_processing_ms"] for row in supported if row.get("common_processing_ms") is not None], .95
        ),
        "model_noise_filter_p95_ms": percentile(
            [row["model_noise_filter_ms"] for row in supported if row.get("model_noise_filter_ms") is not None], .95
        ),
        "false_alarm_frame_examples": [
            row["frame"] for row in supported if row.get("obstacle_candidate_present") is True
        ][:30],
    }
    if args.profile_model_filter:
        totals["model_profile"] = {
            "core_index_extract": timing_stats(supported, "model_profile_core_index_extract_ms"),
            "connected_components_and_features": timing_stats(
                supported, "model_profile_connected_components_and_features_ms"
            ),
            "tree_decision": timing_stats(supported, "model_profile_tree_decision_ms"),
            "output_finalize": timing_stats(supported, "model_profile_output_finalize_ms"),
            "core_index_count_p95": percentile(
                [row["model_profile_core_index_count"] for row in supported], .95
            ),
            "component_count_p95": percentile(
                [row["model_profile_component_count"] for row in supported], .95
            ),
            "neighbor_distance_checks_p95": percentile(
                [row["model_profile_neighbor_distance_checks"] for row in supported], .95
            ),
        }
    totals["fp_frames_per_minute"] = (
        totals["fp_frames"] * 60.0 / totals["duration_seconds"]
        if totals["duration_seconds"] > 0.0 else None
    )
    path = args.output / f"{args.source}.json"
    path.write_text(json.dumps(totals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("DONE " + json.dumps({
        "source": args.source,
        "frames": totals["frames"],
        "fp_frames": totals["fp_frames"],
        "unknown": totals["unknown"],
        "processing_p95_ms": totals["processing_p95_ms"],
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
