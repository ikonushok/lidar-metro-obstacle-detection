"""Train a portable, bounded-depth decision tree for CORE-component noise filtering.

The script is deliberately offline.  It streams each saved source XYZ frame through
the current C++ envelope implementation, reconstructs its connected CORE components,
and trains on the user-approved interval of the one known obstacle.  The saved JSON
is a model artifact, not a permission to turn UNKNOWN into CLEAR.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import time
from collections import Counter


FEATURE_NAMES = (
    "point_count", "extent_x_m", "extent_y_m", "extent_z_m", "volume_m3",
    "density_points_per_m3", "centroid_distance_m", "nearest_distance_m",
)


def connected_components(raw: bytes, source_indices: list[int], radius_m: float) -> list[list[int]]:
    """Return source-index components using the same Euclidean connectivity as C++."""
    if not source_indices:
        return []
    radius2 = radius_m * radius_m
    cells: dict[tuple[int, int, int], list[int]] = {}
    parent = list(range(len(source_indices)))

    def point(local: int) -> tuple[float, float, float]:
        return struct.unpack_from("<fff", raw, source_indices[local] * 12)

    points = [point(local) for local in range(len(source_indices))]

    def root(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        left, right = root(left), root(right)
        if left != right:
            parent[right] = left

    for local, value in enumerate(points):
        cell = tuple(math.floor(axis / radius_m) for axis in value)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in cells.get((cell[0] + dx, cell[1] + dy, cell[2] + dz), []):
                        ox, oy, oz = points[other]
                        if ((value[0] - ox) ** 2 + (value[1] - oy) ** 2 +
                                (value[2] - oz) ** 2 <= radius2):
                            union(local, other)
        cells.setdefault(cell, []).append(local)
    groups: dict[int, list[int]] = {}
    for local, source_index in enumerate(source_indices):
        groups.setdefault(root(local), []).append(source_index)
    return list(groups.values())


def component_features(raw: bytes, component: list[int]) -> list[float]:
    points = [struct.unpack_from("<fff", raw, index * 12) for index in component]
    mins = [min(point[axis] for point in points) for axis in range(3)]
    maxs = [max(point[axis] for point in points) for axis in range(3)]
    extents = [upper - lower for lower, upper in zip(mins, maxs)]
    volume = max(extents[0] * extents[1] * extents[2], 1e-6)
    centre = [sum(point[axis] for point in points) / len(points) for axis in range(3)]
    distances = [math.sqrt(sum(axis * axis for axis in point)) for point in points]
    return [float(len(points)), *extents, volume, len(points) / volume,
            math.sqrt(sum(axis * axis for axis in centre)), min(distances)]


def gini(positive: float, negative: float) -> float:
    total = positive + negative
    if total <= 0:
        return 0.0
    return 1.0 - (positive / total) ** 2 - (negative / total) ** 2


def make_tree(rows: list[dict], depth: int, max_depth: int, min_leaf: int) -> dict:
    positive = sum(row["weight"] for row in rows if row["label"])
    negative = sum(row["weight"] for row in rows if not row["label"])
    node = {"positive_weight": positive, "negative_weight": negative}
    if depth >= max_depth or len(rows) < 2 * min_leaf or not positive or not negative:
        return node
    parent_gini = gini(positive, negative)
    best: tuple[float, int, float, list[dict], list[dict]] | None = None
    for feature in range(len(FEATURE_NAMES)):
        values = sorted({row["features"][feature] for row in rows})
        if len(values) < 2:
            continue
        candidate_positions = sorted({min(len(values) - 2, round((len(values) - 1) * part / 32))
                                      for part in range(1, 32)})
        for position in candidate_positions:
            threshold = (values[position] + values[position + 1]) / 2.0
            left = [row for row in rows if row["features"][feature] <= threshold]
            right = [row for row in rows if row["features"][feature] > threshold]
            if len(left) < min_leaf or len(right) < min_leaf:
                continue
            left_positive = sum(row["weight"] for row in left if row["label"])
            left_negative = sum(row["weight"] for row in left if not row["label"])
            right_positive = positive - left_positive
            right_negative = negative - left_negative
            total = positive + negative
            gain = parent_gini - ((left_positive + left_negative) / total * gini(left_positive, left_negative) +
                                   (right_positive + right_negative) / total * gini(right_positive, right_negative))
            if best is None or gain > best[0]:
                best = gain, feature, threshold, left, right
    if best is None or best[0] <= 1e-9:
        return node
    _, feature, threshold, left, right = best
    node.update({"feature": FEATURE_NAMES[feature], "threshold": threshold,
                 "left": make_tree(left, depth + 1, max_depth, min_leaf),
                 "right": make_tree(right, depth + 1, max_depth, min_leaf)})
    return node


def predict_probability(tree: dict, features: list[float]) -> float:
    node = tree
    feature_positions = {name: index for index, name in enumerate(FEATURE_NAMES)}
    while "feature" in node:
        node = node["left"] if features[feature_positions[node["feature"]]] <= node["threshold"] else node["right"]
    total = node["positive_weight"] + node["negative_weight"]
    return 0.0 if not total else node["positive_weight"] / total


def stream_result(process: subprocess.Popen[bytes], raw: bytes) -> dict:
    process.stdin.write(struct.pack("<Q", len(raw) // 12))
    process.stdin.write(raw)
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError(process.stderr.read().decode(errors="replace"))
    return json.loads(line)


def build_rows(frames_dir: Path, stream_cli: str, positive_first: int, positive_last: int) -> list[dict]:
    frames = sorted(frames_dir.glob("frame_*.xyzf"))
    if len(frames) != 201:
        raise ValueError(f"expected exactly 201 doubleT_obstacle frames, got {len(frames)}")
    process = subprocess.Popen([stream_cli, "2.0"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rows: list[dict] = []
    positive_frames: set[int] = set()
    try:
        for path in frames:
            frame = int(path.stem.split("_")[1])
            raw = path.read_bytes()
            result = stream_result(process, raw)
            core = result.get("core_source_indices", [])
            reportable = set(result.get("reportable_core_source_indices", []))
            components = connected_components(raw, core, 0.25)
            reportable_components = [component for component in components if set(component) <= reportable]
            target_component: set[int] = set()
            if positive_first <= frame <= positive_last:
                if not reportable_components:
                    raise ValueError(f"frame {frame}: no reportable component for known obstacle")
                # The tracked obstacle is the one dominant reportable component in every
                # positive frame.  Smaller reportable components in the same frame are
                # user-labelled noise and must not become positive examples.
                target_component = set(max(reportable_components, key=len))
            for component in components:
                component_set = set(component)
                label = bool(target_component) and component_set == target_component
                if label:
                    positive_frames.add(frame)
                rows.append({"frame": frame, "label": label, "features": component_features(raw, component)})
    finally:
        process.stdin.close()
        process.wait(timeout=5)
    expected = set(range(positive_first, positive_last + 1))
    if positive_frames != expected:
        missing = sorted(expected - positive_frames)
        extra = sorted(positive_frames - expected)
        raise ValueError(f"positive component mismatch; missing={missing}, extra={extra}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--stream-cli", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--min-leaf", type=int, default=5)
    parser.add_argument("--positive-first", type=int, default=13)
    parser.add_argument("--positive-last", type=int, default=64)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite model: {args.output}")
    if args.max_depth < 1 or args.min_leaf < 1 or args.positive_first > args.positive_last:
        raise ValueError("invalid tree or positive-interval parameters")
    rows = build_rows(args.frames_dir, args.stream_cli, args.positive_first, args.positive_last)
    counts = Counter(row["label"] for row in rows)
    if not counts[True] or not counts[False]:
        raise ValueError("training needs both obstacle and noise components")
    for row in rows:
        row["weight"] = 0.5 / counts[row["label"]]
    tree = make_tree(rows, 0, args.max_depth, args.min_leaf)
    samples: list[float] = []
    for _ in range(30):
        started = time.perf_counter_ns()
        for row in rows:
            predict_probability(tree, row["features"])
        samples.append((time.perf_counter_ns() - started) / len(rows) / 1000.0)
    predictions = [predict_probability(tree, row["features"]) >= 0.5 for row in rows]
    tp = sum(pred and row["label"] for pred, row in zip(predictions, rows))
    fp = sum(pred and not row["label"] for pred, row in zip(predictions, rows))
    fn = sum(not pred and row["label"] for pred, row in zip(predictions, rows))
    model = {
        "format": "lidar-component-noise-tree-v1",
        "purpose": "OFFLINE_COMPONENT_CLASSIFICATION_NOT_A_SAFETY_OR_CLEAR_DECISION",
        "features": list(FEATURE_NAMES), "tree": tree,
        "training": {"dataset": "doubleT_obstacle", "frame_count": 201,
                     "positive_frames_inclusive": [args.positive_first, args.positive_last],
                     "positive_label": "known_obstacle_component_from_current_filter",
                     "negative_label": "all_other_core_components_by_user_rule",
                     "connectivity_radius_m": 0.25, "component_count": len(rows),
                     "class_counts": {"obstacle": counts[True], "noise": counts[False]},
                     "model_parameters": {"max_depth": args.max_depth, "min_leaf": args.min_leaf}},
        "development_fit": {"tp": tp, "fp": fp, "fn": fn,
                            "note": "Training-set fit only; no independent positive run exists."},
        "benchmark": {"scope": "Python tree prediction per already-extracted component",
                      "mean_us_per_component": statistics.mean(samples),
                      "p95_us_per_component": sorted(samples)[math.ceil(.95 * len(samples)) - 1],
                      "clock": "time.perf_counter_ns monotonic"},
        "limitations": ["RAW_CORE_AND_UNKNOWN_REMAIN_AUTHORITATIVE_DIAGNOSTICS",
                        "MODEL_NEGATIVE_DOES_NOT_MEAN_CLEAR", "NOT_A_PORTABLE_CXX_RUNTIME_ARTIFACT_YET",
                        "NO_INDEPENDENT_POSITIVE_TEST_OR_GENERALISATION_CLAIM"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "components": len(rows),
                      "obstacle_components": counts[True], "noise_components": counts[False],
                      "development_fit": model["development_fit"], "benchmark": model["benchmark"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
