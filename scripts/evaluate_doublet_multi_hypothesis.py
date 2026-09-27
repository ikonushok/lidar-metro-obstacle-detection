"""Evaluate a tangent OR arc-clamped multi-hypothesis diagnostic.

This script is offline-only.  It does not change runtime behavior or make a
CLEAR/safety decision.  A frame-level union alarm is true when either selected
candidate path reports a candidate_baseline_v2 reportable intrusion candidate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import subprocess


SOURCES = {
    "doubleT_obstacle": ("dataset/for_hackathon/for_hackathon", "for_hackathon/doubleT_obstacle"),
    "roundT_doubleT": ("dataset/for_hackathon/for_hackathon", "for_hackathon/roundT_doubleT"),
    "roundT_pressureGate_roundT": (
        "dataset/for_hackathon/for_hackathon", "for_hackathon/roundT_pressureGate_roundT"),
}


def start_stream(stream_cli: str, args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        [stream_cli, "2.0", *args, "--use-model-filter"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def stream_result(process: subprocess.Popen, raw: bytes) -> dict:
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("stream process pipes are unavailable")
    process.stdin.write(struct.pack("<Q", len(raw) // 12))
    process.stdin.write(raw)
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
        raise RuntimeError("C++ stream ended unexpectedly: " + stderr[-1000:])
    result = json.loads(line)
    if result.get("safety_decision_permitted") is not False:
        raise ValueError("candidate stream must remain safety_decision_permitted=false")
    if result.get("noise_filter_mode") != "candidate_baseline_v2":
        raise ValueError("expected candidate_baseline_v2 active filter")
    return result


def alarm(result: dict) -> bool:
    return result.get("reportable_intrusion_candidate_present") is True


def summarize(rows: list[dict], positive_first: int | None, positive_last: int | None) -> dict:
    positive = [row for row in rows if row["target"]]
    negative = [row for row in rows if not row["target"]]
    summary = {
        "frame_count": len(rows),
        "positive_interval_inclusive": (
            [positive_first, positive_last]
            if positive_first is not None and positive_last is not None else None),
        "positive_frames": len(positive),
        "negative_frames": len(negative),
    }
    for method in ("tangent", "arc_clamped", "union"):
        summary[method] = {
            "alarm_frames": sum(row[method + "_alarm"] for row in rows),
            "tp_frames": sum(row["target"] and row[method + "_alarm"] for row in rows),
            "fn_frames": sum(row["target"] and not row[method + "_alarm"] for row in rows),
            "fp_frames": sum(not row["target"] and row[method + "_alarm"] for row in rows),
            "tn_frames": sum(not row["target"] and not row[method + "_alarm"] for row in rows),
            "alarm_frame_indices": [row["frame"] for row in rows if row[method + "_alarm"]],
            "fp_frame_indices": [row["frame"] for row in rows if not row["target"] and row[method + "_alarm"]],
            "fn_frame_indices": [row["frame"] for row in rows if row["target"] and not row[method + "_alarm"]],
        }
    summary["arc_added_alarm_frame_indices"] = [
        row["frame"] for row in rows if row["arc_clamped_alarm"] and not row["tangent_alarm"]]
    summary["union_added_alarm_frame_indices"] = [
        row["frame"] for row in rows if row["union_alarm"] and not row["tangent_alarm"]]
    summary["pass_doublet_obstacle_gate"] = None
    if positive_first is not None and positive_last is not None:
        summary["pass_doublet_obstacle_gate"] = (
            summary["union"]["tp_frames"] == len(positive) and
            summary["union"]["fn_frames"] == 0 and
            summary["union"]["fp_frames"] == 0
        )
    return summary


def close_stream(process: subprocess.Popen) -> None:
    if process.stdin is not None:
        process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def evaluate(args: argparse.Namespace) -> dict:
    from archive_bag_frames import ArchiveBagFrames

    archive_path, prefix = SOURCES[args.source]
    source = ArchiveBagFrames(
        args.root / archive_path,
        prefix,
        args.source,
    )
    tangent = start_stream(args.stream_cli, [])
    arc = start_stream(
        args.stream_cli,
        [
            "--arc-clamped",
            str(args.arc_extension_horizon_m),
            str(args.min_arc_radius_m),
            str(args.max_arc_turn_deg),
            "--arc-fit-window",
            str(args.arc_fit_window_pairs),
        ],
    )
    rows: list[dict] = []
    try:
        last = len(source.lookup) - 1 if args.last is None else min(args.last, len(source.lookup) - 1)
        if args.first < 0 or last < args.first:
            raise ValueError("invalid frame range")
        for frame in range(args.first, last + 1):
            record, raw = source.frame(frame)
            tangent_result = stream_result(tangent, raw)
            arc_result = stream_result(arc, raw)
            tangent_alarm = alarm(tangent_result)
            arc_alarm = alarm(arc_result)
            row = {
                "frame": frame,
                "target": (
                    args.positive_first is not None and args.positive_last is not None and
                    args.positive_first <= frame <= args.positive_last),
                "header_timestamp_ns": str(record["header_timestamp_ns"]),
                "tangent_alarm": tangent_alarm,
                "arc_clamped_alarm": arc_alarm,
                "union_alarm": tangent_alarm or arc_alarm,
                "tangent_status": tangent_result.get("status"),
                "arc_clamped_status": arc_result.get("status"),
                "tangent_reportable_core_count": tangent_result.get("reportable_core_count"),
                "arc_clamped_reportable_core_count": arc_result.get("reportable_core_count"),
                "tangent_nearest_m": tangent_result.get("nearest_reportable_intrusion_distance_from_source_origin_m"),
                "arc_clamped_nearest_m": arc_result.get("nearest_reportable_intrusion_distance_from_source_origin_m"),
                "arc_clamped_forward_status": arc_result.get("forward_extension_status"),
                "arc_clamped_applied_horizon_m": arc_result.get("forward_extension_applied_horizon_m"),
            }
            rows.append(row)
    finally:
        source.close()
        close_stream(tangent)
        close_stream(arc)
    summary = {
        "format": "doublet-multi-hypothesis-eval-v1",
        "scope": "OFFLINE_DIAGNOSTIC_NOT_RUNTIME_OR_SAFETY_DECISION",
        "source": args.source,
        "variant": "tangent OR arc_clamped",
        "runtime_default_unchanged": True,
        "noise_filter_mode": "candidate_baseline_v2",
        "arc_clamped_config": {
            "arc_extension_horizon_m": args.arc_extension_horizon_m,
            "min_arc_radius_m": args.min_arc_radius_m,
            "max_arc_turn_deg": args.max_arc_turn_deg,
            "arc_fit_window_pairs": args.arc_fit_window_pairs,
        },
        "metrics": summarize(rows, args.positive_first, args.positive_last),
        "limitations": [
            "Union preserves tangent detections by construction and may increase false positives.",
            "Passing doubleT_obstacle is required but not sufficient for curved-path readiness.",
            "No p95 runtime, ROS2 queueing, TF, deskew, or held-out route validation is claimed.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    details_path = args.output.with_name(args.output.stem + "_frames.jsonl")
    with details_path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"summary": summary, "frames": str(details_path)}, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/workspace"))
    parser.add_argument("--source", choices=tuple(SOURCES), default="doubleT_obstacle")
    parser.add_argument("--stream-cli", default="/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--last", type=int)
    parser.add_argument("--positive-first", type=int)
    parser.add_argument("--positive-last", type=int)
    parser.add_argument("--arc-extension-horizon-m", type=float, default=5.0)
    parser.add_argument("--min-arc-radius-m", type=float, default=60.0)
    parser.add_argument("--max-arc-turn-deg", type=float, default=4.0)
    parser.add_argument("--arc-fit-window-pairs", type=int, default=7)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.source == "doubleT_obstacle" and args.positive_first is None and args.positive_last is None:
        args.positive_first = 13
        args.positive_last = 64
    if (args.positive_first is None) != (args.positive_last is None):
        raise ValueError("positive interval must provide both endpoints")
    if args.positive_first is not None and args.positive_last < args.positive_first:
        raise ValueError("invalid positive interval")
    evaluate(args)


if __name__ == "__main__":
    main()
