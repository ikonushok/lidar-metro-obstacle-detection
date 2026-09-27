"""Offline benchmark for predicting a hidden tail of observed rail pairs.

This diagnostic hides the last N observed rail-pairs in each supported frame,
predicts their centreline positions from the visible prefix, and compares the
prediction with the hidden observations.  It does not change runtime behavior
and does not make obstacle, CLEAR, or safety claims.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import time
from typing import Iterable


SOURCES = {
    "roundT_doubleT": ("dataset/for_hackathon/for_hackathon", "for_hackathon/roundT_doubleT"),
    "squareT_platform_squareT_switch": (
        "dataset/for_hackathon/for_hackathon", "for_hackathon/squareT_platform_squareT_switch"),
    "doubleT_platform": ("dataset/for_hackathon/for_hackathon", "for_hackathon/doubleT_platform"),
    "roundT_squareT_pressureGate_squareT": (
        "dataset/for_hackathon/for_hackathon", "for_hackathon/roundT_squareT_pressureGate_squareT"),
    "doubleT_obstacle": ("dataset/for_hackathon/for_hackathon", "for_hackathon/doubleT_obstacle"),
    "roundT_pressureGate_roundT": (
        "dataset/for_hackathon/for_hackathon", "for_hackathon/roundT_pressureGate_roundT"),
    "new_data": ("dataset/for_hackathon/new_data", "new_data"),
}


@dataclass(frozen=True)
class Center:
    source_s_m: float
    x: float
    y: float
    z: float


@dataclass
class RidgeStepModel:
    coefficients: list[list[float]]
    ridge_lambda: float


def pair_center(pair: dict) -> Center:
    left = pair["left_xyz"]
    right = pair["right_xyz"]
    return Center(
        float(pair["source_s_m"]),
        (float(left[0]) + float(right[0])) * 0.5,
        (float(left[1]) + float(right[1])) * 0.5,
        (float(left[2]) + float(right[2])) * 0.5,
    )


def observed_centers(result: dict) -> list[Center]:
    pairs = result.get("rail_pairs_source_xyz", [])
    return [pair_center(pair) for pair in pairs if pair.get("observed", True)]


def tangent_predict(prefix: list[Center], target_s: float) -> Center | None:
    if len(prefix) < 2:
        return None
    before, last = prefix[-2], prefix[-1]
    ds = last.source_s_m - before.source_s_m
    if ds <= 1e-9:
        return None
    scale = (target_s - last.source_s_m) / ds
    return Center(
        target_s,
        last.x + (last.x - before.x) * scale,
        last.y + (last.y - before.y) * scale,
        last.z + (last.z - before.z) * scale,
    )


def solve_3x3(matrix: list[list[float]]) -> list[float] | None:
    rows = [row[:] for row in matrix]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) <= 1e-12:
            return None
        if pivot != column:
            rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        for item in range(column, 4):
            rows[column][item] /= divisor
        for row in range(3):
            if row == column:
                continue
            factor = rows[row][column]
            for item in range(column, 4):
                rows[row][item] -= factor * rows[column][item]
    return [rows[index][3] for index in range(3)]


def fit_circle(points: list[Center]) -> tuple[float, float, float, float] | None:
    if len(points) < 3:
        return None
    normal = [[0.0, 0.0, 0.0, 0.0] for _ in range(3)]
    for point in points:
        row = [point.x, point.y, 1.0]
        rhs = -(point.x * point.x + point.y * point.y)
        for r in range(3):
            for c in range(3):
                normal[r][c] += row[r] * row[c]
            normal[r][3] += row[r] * rhs
    solution = solve_3x3(normal)
    if solution is None:
        return None
    centre_x = -solution[0] * 0.5
    centre_y = -solution[1] * 0.5
    radius2 = centre_x * centre_x + centre_y * centre_y - solution[2]
    if not math.isfinite(radius2) or radius2 <= 1e-9:
        return None
    radius = math.sqrt(radius2)
    last, before = points[-1], points[-2]
    radial_x = last.x - centre_x
    radial_y = last.y - centre_y
    if math.hypot(radial_x, radial_y) <= 1e-9:
        return None
    motion_x = last.x - before.x
    motion_y = last.y - before.y
    ccw_x, ccw_y = -radial_y, radial_x
    direction = 1.0 if ccw_x * motion_x + ccw_y * motion_y >= 0.0 else -1.0
    return centre_x, centre_y, radius, direction


def arc_predict(prefix: list[Center], target_s: float, *, window: int,
                min_radius_m: float = 0.0, max_turn_deg: float | None = None) -> Center | None:
    if len(prefix) < 3:
        return None
    fit_points = prefix[-max(3, min(window, len(prefix))):]
    circle = fit_circle(fit_points)
    if circle is None:
        return None
    centre_x, centre_y, radius, direction = circle
    if radius < min_radius_m:
        return None
    last, before = prefix[-1], prefix[-2]
    distance = target_s - last.source_s_m
    if distance <= 0.0:
        return None
    if max_turn_deg is not None:
        max_horizon = radius * math.radians(max_turn_deg)
        if distance > max_horizon + 1e-9:
            return None
    angle = direction * distance / radius
    dx = last.x - centre_x
    dy = last.y - centre_y
    cosine = math.cos(angle)
    sine = math.sin(angle)
    ds = last.source_s_m - before.source_s_m
    if ds <= 1e-9:
        return None
    z = last.z + (last.z - before.z) * distance / ds
    return Center(
        target_s,
        centre_x + cosine * dx - sine * dy,
        centre_y + sine * dx + cosine * dy,
        z,
    )


def ml_features(prefix: list[Center], target_s: float) -> list[float] | None:
    if len(prefix) < 3:
        return None
    a, b, c = prefix[-3], prefix[-2], prefix[-1]
    ds0 = b.source_s_m - a.source_s_m
    ds1 = c.source_s_m - b.source_s_m
    step = target_s - c.source_s_m
    if ds0 <= 1e-9 or ds1 <= 1e-9 or step <= 0.0:
        return None
    v0 = [(b.x - a.x) / ds0, (b.y - a.y) / ds0, (b.z - a.z) / ds0]
    v1 = [(c.x - b.x) / ds1, (c.y - b.y) / ds1, (c.z - b.z) / ds1]
    accel = [v1[axis] - v0[axis] for axis in range(3)]
    return [
        1.0, step, step * step,
        v1[0] * step, v1[1] * step, v1[2] * step,
        accel[0] * step * step, accel[1] * step * step, accel[2] * step * step,
    ]


def gaussian_solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    rows = [matrix[row][:] + [rhs[row]] for row in range(len(rhs))]
    size = len(rhs)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) <= 1e-12:
            raise ValueError("singular ridge system")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        for item in range(column, size + 1):
            rows[column][item] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            for item in range(column, size + 1):
                rows[row][item] -= factor * rows[column][item]
    return [rows[index][size] for index in range(size)]


def train_ridge_step_model(frames: list[list[Center]], ridge_lambda: float) -> RidgeStepModel:
    feature_rows: list[list[float]] = []
    labels: list[list[float]] = []
    for centers in frames:
        for index in range(3, len(centers)):
            prefix = centers[:index]
            features = ml_features(prefix, centers[index].source_s_m)
            if features is None:
                continue
            last = prefix[-1]
            target = centers[index]
            feature_rows.append(features)
            labels.append([target.x - last.x, target.y - last.y, target.z - last.z])
    if not feature_rows:
        raise ValueError("no ML training examples; need frames with at least four rail pairs")
    feature_count = len(feature_rows[0])
    xtx = [[0.0 for _ in range(feature_count)] for _ in range(feature_count)]
    xty = [[0.0, 0.0, 0.0] for _ in range(feature_count)]
    for features, label in zip(feature_rows, labels):
        for row in range(feature_count):
            xty[row][0] += features[row] * label[0]
            xty[row][1] += features[row] * label[1]
            xty[row][2] += features[row] * label[2]
            for column in range(feature_count):
                xtx[row][column] += features[row] * features[column]
    for index in range(feature_count):
        xtx[index][index] += ridge_lambda
    coefficients = []
    for axis in range(3):
        coefficients.append(gaussian_solve(xtx, [row[axis] for row in xty]))
    return RidgeStepModel(coefficients=coefficients, ridge_lambda=ridge_lambda)


def ml_predict(prefix: list[Center], target_s: float, model: RidgeStepModel) -> Center | None:
    features = ml_features(prefix, target_s)
    if features is None:
        return None
    delta = [sum(weight * value for weight, value in zip(axis, features))
             for axis in model.coefficients]
    last = prefix[-1]
    return Center(target_s, last.x + delta[0], last.y + delta[1], last.z + delta[2])


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(len(values) * fraction) - 1)]


def evaluate_predictions(rows: list[dict]) -> dict:
    xy_errors = [row["xy_error_m"] for row in rows if row["xy_error_m"] is not None]
    z_errors = [abs(row["z_error_m"]) for row in rows if row["z_error_m"] is not None]
    return {
        "target_count": len(rows),
        "predicted_count": len(xy_errors),
        "missing_count": len(rows) - len(xy_errors),
        "coverage": len(xy_errors) / len(rows) if rows else 0.0,
        "mean_xy_error_m": statistics.mean(xy_errors) if xy_errors else None,
        "p50_xy_error_m": percentile(xy_errors, 0.50),
        "p95_xy_error_m": percentile(xy_errors, 0.95),
        "max_xy_error_m": max(xy_errors) if xy_errors else None,
        "mean_abs_z_error_m": statistics.mean(z_errors) if z_errors else None,
    }


def predict_tail(prefix: list[Center], hidden: list[Center], method: str,
                 model: RidgeStepModel | None, args: argparse.Namespace) -> list[dict]:
    working = list(prefix)
    rows = []
    for target in hidden:
        if method == "tangent":
            prediction = tangent_predict(working, target.source_s_m)
        elif method == "arc_last3":
            prediction = arc_predict(working, target.source_s_m, window=3)
        elif method == "arc_window_clamped":
            prediction = arc_predict(
                working, target.source_s_m, window=args.arc_fit_window_pairs,
                min_radius_m=args.min_arc_radius_m, max_turn_deg=args.max_arc_turn_deg)
        elif method == "ml_ridge_step":
            if model is None:
                raise ValueError("ML model was not trained")
            prediction = ml_predict(working, target.source_s_m, model)
        else:
            raise ValueError(f"unknown method: {method}")
        if prediction is None:
            rows.append({"source_s_m": target.source_s_m, "xy_error_m": None, "z_error_m": None})
            break
        xy_error = math.hypot(prediction.x - target.x, prediction.y - target.y)
        rows.append({
            "source_s_m": target.source_s_m,
            "xy_error_m": xy_error,
            "z_error_m": prediction.z - target.z,
            "predicted_xyz": [prediction.x, prediction.y, prediction.z],
            "target_xyz": [target.x, target.y, target.z],
        })
        working.append(prediction)
    if len(rows) < len(hidden):
        for target in hidden[len(rows):]:
            rows.append({"source_s_m": target.source_s_m, "xy_error_m": None, "z_error_m": None})
    return rows


def split_frames(frames: list[dict], train_fraction: float) -> tuple[list[dict], list[dict]]:
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train fraction must be between 0 and 1")
    cutoff = max(1, min(len(frames) - 1, round(len(frames) * train_fraction)))
    return frames[:cutoff], frames[cutoff:]


def stream_observed_rails(root: Path, source_id: str, stream_cli: str, first: int,
                          last: int | None, rail_forward_min_m: float) -> list[dict]:
    from archive_bag_frames import ArchiveBagFrames

    archive_path, prefix = SOURCES[source_id]
    source = ArchiveBagFrames(root / archive_path, prefix, source_id)
    process = subprocess.Popen(
        [stream_cli, str(float(rail_forward_min_m)), "--arc-limited", "0"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    rows = []
    try:
        final = len(source.lookup) - 1 if last is None else min(last, len(source.lookup) - 1)
        if first < 0 or final < first:
            raise ValueError("invalid frame range")
        for index in range(first, final + 1):
            record, raw = source.frame(index)
            process.stdin.write(struct.pack("<Q", len(raw) // 12))
            process.stdin.write(raw)
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                stderr = process.stderr.read().decode(errors="replace")
                raise RuntimeError(f"C++ stream stopped on {source_id} frame {index}: {stderr[-1000:]}")
            result = json.loads(line)
            if result.get("safety_decision_permitted") is not False:
                raise ValueError("stream result must remain candidate-only")
            centers = observed_centers(result)
            rows.append({
                "frame": index,
                "bag_offset_seconds": record["bag_offset_seconds"],
                "status": result.get("status"),
                "curve_axis_status": result.get("curve_axis_status"),
                "reason": result.get("reason"),
                "centers": centers,
                "observed_rail_pair_count": len(centers),
                "stream_processing_ms": result.get("processing_ms"),
            })
    finally:
        source.close()
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    return rows


def serializable_center(center: Center) -> dict:
    return {"source_s_m": center.source_s_m, "xyz": [center.x, center.y, center.z]}


def run_benchmark(frames: list[dict], args: argparse.Namespace) -> dict:
    eligible = [
        frame for frame in frames
        if len(frame["centers"]) >= args.min_prefix_pairs + args.hide_pairs
    ]
    if len(eligible) < 2:
        raise ValueError("not enough eligible frames for train/eval split")
    train_frames, eval_frames = split_frames(eligible, args.train_fraction)
    model = train_ridge_step_model([frame["centers"] for frame in train_frames], args.ridge_lambda)
    methods = ["tangent", "arc_last3", "arc_window_clamped", "ml_ridge_step"]
    all_rows = {method: [] for method in methods}
    per_frame = []
    for frame in eval_frames:
        centers = frame["centers"]
        prefix = centers[:-args.hide_pairs]
        hidden = centers[-args.hide_pairs:]
        frame_record = {
            "frame": frame["frame"],
            "observed_rail_pair_count": frame["observed_rail_pair_count"],
            "prefix_pair_count": len(prefix),
            "hidden_pair_count": len(hidden),
            "prefix_end_s_m": prefix[-1].source_s_m,
            "prefix": [serializable_center(center) for center in prefix],
            "hidden": [serializable_center(center) for center in hidden],
            "methods": {},
        }
        for method in methods:
            rows = predict_tail(prefix, hidden, method, model, args)
            all_rows[method].extend({"frame": frame["frame"], **row} for row in rows)
            frame_record["methods"][method] = {
                "summary": evaluate_predictions(rows),
                "predictions": rows,
            }
        per_frame.append(frame_record)
    return {
        "format": "hidden-rail-tail-benchmark-v1",
        "scope": "OFFLINE_DEVELOPMENT_DIAGNOSTIC_NOT_RUNTIME_OR_SAFETY_DECISION",
        "source": args.source,
        "frame_range_inclusive": [args.first, args.last],
        "rail_forward_min_m": args.rail_forward_min_m,
        "collection_mode": "curve_pipeline_stream_cli --arc-limited 0 for observed rail pairs only",
        "hide_pairs": args.hide_pairs,
        "min_prefix_pairs": args.min_prefix_pairs,
        "eligible_frames": len(eligible),
        "train_frames": [frame["frame"] for frame in train_frames],
        "eval_frames": [frame["frame"] for frame in eval_frames],
        "ml_model": {
            "type": "ridge_linear_next_step",
            "ridge_lambda": model.ridge_lambda,
            "feature_count": len(model.coefficients[0]),
            "train_fraction": args.train_fraction,
            "note": "Trained only to predict the next observed rail-pair centre; not used by runtime.",
        },
        "arc_window_clamped_config": {
            "min_arc_radius_m": args.min_arc_radius_m,
            "max_arc_turn_deg": args.max_arc_turn_deg,
            "arc_fit_window_pairs": args.arc_fit_window_pairs,
        },
        "summary": {method: evaluate_predictions(rows) for method, rows in all_rows.items()},
        "per_frame": per_frame,
        "limitations": [
            "Uses observed rail-pairs as provisional self-supervised labels, not rail ground truth.",
            "A better hidden-tail score does not prove better obstacle detection.",
            "No frame, TF, deskew, profile, margin, candidate_baseline_v2, or safety decision is changed.",
        ],
    }


def write_outputs(output: Path, report: dict) -> None:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)
    summary = dict(report)
    per_frame = summary.pop("per_frame")
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "per_frame.jsonl").open("w", encoding="utf-8") as stream:
        for row in per_frame:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/workspace"))
    parser.add_argument("--source", choices=tuple(SOURCES), default="doubleT_obstacle")
    parser.add_argument("--stream-cli", default="/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--last", type=int)
    parser.add_argument("--rail-forward-min-m", type=float, default=2.0)
    parser.add_argument("--hide-pairs", type=int, default=3)
    parser.add_argument("--min-prefix-pairs", type=int, default=4)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--ridge-lambda", type=float, default=1e-3)
    parser.add_argument("--min-arc-radius-m", type=float, default=60.0)
    parser.add_argument("--max-arc-turn-deg", type=float, default=8.0)
    parser.add_argument("--arc-fit-window-pairs", type=int, default=5)
    args = parser.parse_args()
    if args.hide_pairs < 1 or args.min_prefix_pairs < 3:
        raise ValueError("hide-pairs must be >=1 and min-prefix-pairs must be >=3")
    if args.ridge_lambda < 0.0 or args.min_arc_radius_m <= 0.0 or args.max_arc_turn_deg <= 0.0:
        raise ValueError("invalid ML or arc parameters")
    started = time.monotonic()
    frames = stream_observed_rails(args.root, args.source, args.stream_cli, args.first,
                                   args.last, args.rail_forward_min_m)
    if args.last is None:
        args.last = frames[-1]["frame"] if frames else args.first
    report = run_benchmark(frames, args)
    report["wall_seconds"] = time.monotonic() - started
    write_outputs(args.output, report)
    print(json.dumps({
        "output": str(args.output),
        "eligible_frames": report["eligible_frames"],
        "eval_frames": len(report["eval_frames"]),
        "summary": report["summary"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
