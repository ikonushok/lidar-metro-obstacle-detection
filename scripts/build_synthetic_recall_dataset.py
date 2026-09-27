"""Build a development synthetic recall dataset with frozen splits.

The builder creates manifest rows, point-label sidecars, component rows, and
baseline candidate_baseline_v2 matching for synthetic placements on compact real XYZ frames.
It deliberately does not train models and does not change runtime defaults.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from archive_bag_frames import ArchiveBagFrames  # noqa: E402
from synthetic_obstacle_generator import load_synthetic_config, raycast_scene, scenario_catalog  # noqa: E402
from train_noise_classifier import component_features, connected_components  # noqa: E402


SOURCES = {
    "roundT_doubleT": ("for_hackathon/roundT_doubleT", "for_hackathon"),
    "squareT_platform_squareT_switch": ("for_hackathon/squareT_platform_squareT_switch", "for_hackathon"),
    "doubleT_platform": ("for_hackathon/doubleT_platform", "for_hackathon"),
    "roundT_squareT_pressureGate_squareT": ("for_hackathon/roundT_squareT_pressureGate_squareT", "for_hackathon"),
    "doubleT_obstacle": ("for_hackathon/doubleT_obstacle", "for_hackathon"),
    "roundT_pressureGate_roundT": ("for_hackathon/roundT_pressureGate_roundT", "for_hackathon"),
    "new_data": ("new_data", "new_data"),
}
DEFAULT_DISTANCES_M = (10.0, 30.0, 60.0)
DEFAULT_ZONE_OFFSETS_M = {"center": 0.0, "left_boundary": -0.95, "right_boundary": 0.95}
LOW_THIN_SCENARIOS = {"low_box", "crowbar", "shovel", "jacket_bundle", "pipe_across_track", "cable"}
SPLIT_POLICIES = ("legacy_v1", "all_train", "all_synthetic_held_out")


def raw_xyz(points: np.ndarray) -> bytes:
    return np.ascontiguousarray(points, dtype="<f4").tobytes()


def write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def primitive_items(obstacle: dict) -> list[dict]:
    return obstacle.get("parts") or [obstacle]


def scenario_center(scenario: dict) -> np.ndarray:
    centers = []
    for obstacle in scenario["objects"]:
        for primitive in primitive_items(obstacle):
            centers.append(np.asarray(primitive["center_xyz"], dtype=np.float64))
    if not centers:
        raise ValueError(f"{scenario['id']}: no primitive centers")
    return np.vstack(centers).mean(axis=0)


def placed_scenario(scenario: dict, distance_m: float, zone_id: str, lateral_offset_m: float) -> dict:
    """Return a deep-copied scenario shifted to requested source-frame placement."""
    placed = copy.deepcopy(scenario)
    current = scenario_center(scenario)
    target = np.array([lateral_offset_m, -abs(float(distance_m)), current[2]], dtype=np.float64)
    delta = target - current
    for obstacle in placed["objects"]:
        for primitive in primitive_items(obstacle):
            center = np.asarray(primitive["center_xyz"], dtype=np.float64) + delta
            primitive["center_xyz"] = [float(value) for value in center]
    placed["id"] = f"{scenario['id']}__d{int(distance_m):03d}__{zone_id}"
    placed["base_scenario_id"] = scenario["id"]
    placed["placement"] = {
        "distance_m": float(distance_m),
        "zone_id": zone_id,
        "lateral_offset_m": float(lateral_offset_m),
        "shift_xyz_m": [float(value) for value in delta],
    }
    return placed


def config_for_scenario(config: dict, scenario: dict) -> dict:
    derived = copy.deepcopy(config)
    derived.pop("obstacles", None)
    derived["scenarios"] = [scenario]
    derived["scenario_selection"] = {"mode": "fixed", "default_scenario_id": scenario["id"]}
    return derived


def split_for(base_scenario_id: str, distance_m: float, zone_id: str, source_id: str, frame_index: int,
              policy: str) -> str:
    if policy == "all_train":
        return "train"
    if policy == "all_synthetic_held_out":
        return "synthetic_held_out"
    if policy != "legacy_v1":
        raise ValueError(f"unsupported split policy: {policy}")
    if source_id == "doubleT_obstacle" and 13 <= frame_index <= 64:
        return "real_regression"
    if zone_id == "right_boundary" or int(round(distance_m)) == 60:
        return "synthetic_held_out"
    if zone_id == "left_boundary":
        return "calibration"
    if base_scenario_id in {"low_box", "cable"} and int(round(distance_m)) in {10, 30}:
        return "synthetic_held_out"
    return "train"


def split_policy_rules(policy: str) -> list[str]:
    if policy == "all_train":
        return [
            "every generated placement -> train",
            "use only with source-window/background groups reserved for training",
        ]
    if policy == "all_synthetic_held_out":
        return [
            "every generated placement -> synthetic_held_out",
            "use only with source-window/background groups excluded from model selection",
        ]
    if policy == "legacy_v1":
        return [
            "doubleT_obstacle frames 13-64 -> real_regression",
            "right_boundary or 60m placements -> synthetic_held_out",
            "left_boundary placements -> calibration",
            "low_box/cable at 10m/30m -> synthetic_held_out probe",
            "remaining placements -> train",
        ]
    raise ValueError(f"unsupported split policy: {policy}")


def stream_result(process: subprocess.Popen[bytes], raw: bytes, row_id: str) -> dict:
    try:
        process.stdin.write(struct.pack("<Q", len(raw) // 12))
        process.stdin.write(raw)
        process.stdin.flush()
    except BrokenPipeError as exc:
        stderr = process.stderr.read().decode(errors="replace")[-1000:]
        raise RuntimeError(f"{row_id}: stream pipe closed: {stderr}") from exc
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read().decode(errors="replace")[-1000:]
        raise RuntimeError(f"{row_id}: stream stopped: {stderr}")
    return json.loads(line)


def component_rows(points: np.ndarray, labels: np.ndarray, result: dict) -> tuple[list[dict], dict]:
    if result.get("status") == "UNKNOWN":
        return [], {
            "status": "UNKNOWN",
            "unknown": True,
            "positive_components": 0,
            "model_tp_components": 0,
            "model_fn_components": 0,
            "model_fp_components": 0,
            "legacy_reportable_components": 0,
            "model_reportable_components": 0,
            "core_component_count": 0,
        }
    raw = raw_xyz(points)
    groups = connected_components(raw, result.get("core_source_indices", []), 0.25)
    legacy_reportable = set(result.get("reportable_core_source_indices", []))
    model_reportable = set(result.get("model_reportable_core_source_indices", legacy_reportable))
    rows = []
    totals = Counter()
    for component_id, component in enumerate(groups):
        component_set = set(component)
        synthetic_indices = [index for index in component if int(labels[index]) >= 0]
        positive = bool(synthetic_indices)
        legacy_hit = component_set <= legacy_reportable
        model_hit = component_set <= model_reportable
        if positive:
            totals["positive_components"] += 1
            totals["model_tp_components" if model_hit else "model_fn_components"] += 1
        elif model_hit:
            totals["model_fp_components"] += 1
        rows.append({
            "component_id": component_id,
            "source_indices": component,
            "point_count": len(component),
            "synthetic_point_count": len(synthetic_indices),
            "matched_object_labels": sorted({int(labels[index]) for index in synthetic_indices}),
            "legacy_reportable": legacy_hit,
            "candidate_baseline_v2_reportable": model_hit,
            "features": component_features(raw, component),
        })
    return rows, {
        "status": result.get("status"),
        "unknown": False,
        "positive_components": totals["positive_components"],
        "model_tp_components": totals["model_tp_components"],
        "model_fn_components": totals["model_fn_components"],
        "model_fp_components": totals["model_fp_components"],
        "legacy_reportable_components": sum(row["legacy_reportable"] for row in rows),
        "model_reportable_components": sum(row["candidate_baseline_v2_reportable"] for row in rows),
        "core_component_count": len(rows),
    }


def label_sidecar(labels: np.ndarray, scenario: dict) -> dict:
    rows = []
    for index, label in enumerate(labels.tolist()):
        if label < 0:
            continue
        obstacle = scenario["objects"][label]
        rows.append({
            "point_index": index,
            "object_label": int(label),
            "object_id": obstacle["id"],
            "category": obstacle.get("category", "UNSPECIFIED"),
            "synthetic_return": True,
        })
    return {
        "format": "synthetic_point_labels_sparse_v1",
        "point_count": int(len(labels)),
        "default": {
            "object_label": -1,
            "object_id": None,
            "category": None,
            "synthetic_return": False,
        },
        "labels": rows,
    }


def parse_source_window(value: str) -> tuple[str, int, int]:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] not in SOURCES:
        raise argparse.ArgumentTypeError("source window must be SOURCE:FIRST:COUNT")
    first = int(parts[1])
    count = int(parts[2])
    if first < 0 or count < 1:
        raise argparse.ArgumentTypeError("invalid source window range")
    return parts[0], first, count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "synthetic_obstacles_development.yaml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stream-cli", default="/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    parser.add_argument("--source-window", action="append", type=parse_source_window, default=[])
    parser.add_argument("--distance-m", action="append", type=float, default=[])
    parser.add_argument("--zone", action="append", default=[])
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--dataset-version", default="synthetic_obstacles_v1_seeded_splits")
    parser.add_argument("--split-policy", choices=SPLIT_POLICIES, default="legacy_v1")
    args = parser.parse_args()

    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty output: {args.output}")
    config = load_synthetic_config(args.config)
    base_scenarios = {scenario["id"]: scenario for scenario in scenario_catalog(config)}
    scenario_ids = args.scenario or sorted(base_scenarios)
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in base_scenarios]
    if missing:
        raise ValueError(f"unknown scenario ids: {missing}")
    distances = args.distance_m or list(DEFAULT_DISTANCES_M)
    zone_offsets = dict(DEFAULT_ZONE_OFFSETS_M)
    zones = args.zone or list(zone_offsets)
    unknown_zones = [zone for zone in zones if zone not in zone_offsets]
    if unknown_zones:
        raise ValueError(f"unknown zones: {unknown_zones}")
    source_windows = args.source_window or [("doubleT_obstacle", 0, 2)]

    config_sha256 = hashlib.sha256(args.config.read_bytes()).hexdigest()
    placements = [
        placed_scenario(base_scenarios[scenario_id], distance, zone_id, zone_offsets[zone_id])
        for scenario_id in scenario_ids
        for distance in distances
        for zone_id in zones
    ]

    args.output.mkdir(parents=True, exist_ok=True)
    for child in ("ground_truth", "point_labels", "component_rows", "baseline_candidate_baseline_v2", "checkpoints", "trained_models"):
        (args.output / child).mkdir(exist_ok=True)

    manifest_rows = []
    all_component_rows = []
    visibility_failures = []
    split_counts = Counter()
    baseline_totals = Counter()
    slice_metrics: dict[str, Counter] = defaultdict(Counter)

    process = subprocess.Popen(
        [args.stream_cli, "2.0", "--compare-noise-filters"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for source_id, first, count in source_windows:
            prefix, archive_name = SOURCES[source_id]
            source = ArchiveBagFrames(args.root / "dataset" / "for_hackathon" / archive_name, prefix, source_id)
            try:
                last = min(first + count - 1, len(source.lookup) - 1)
                for frame_index in range(first, last + 1):
                    record, raw = source.frame(frame_index)
                    if record["source_frame"] != config["source_frame"]:
                        raise ValueError(
                            f"SOURCE_FRAME_MISMATCH:{record['source_frame']}!={config['source_frame']}"
                        )
                    source_points = np.frombuffer(raw, dtype="<f4").reshape(-1, 3).astype(np.float64)
                    for scenario in placements:
                        base_id = scenario["base_scenario_id"]
                        placement = scenario["placement"]
                        split = split_for(
                            base_id, placement["distance_m"], placement["zone_id"],
                            source_id, frame_index, args.split_policy,
                        )
                        placed_config = config_for_scenario(config, scenario)
                        augmented, labels, truth = raycast_scene(
                            source_points, placed_config, frame_index=frame_index, scenario_id=scenario["id"]
                        )
                        row_id = (
                            f"{source_id}_frame_{frame_index:04d}_{base_id}_"
                            f"d{int(placement['distance_m']):03d}_{placement['zone_id']}"
                        )
                        result = stream_result(process, raw_xyz(augmented), row_id)
                        if result.get("safety_decision_permitted") is not False:
                            raise ValueError(f"{row_id}: safety contract changed")
                        components, component_summary = component_rows(augmented, labels, result)
                        for row in components:
                            row.update({
                                "row_id": row_id,
                                "source_id": source_id,
                                "source_frame_index": frame_index,
                                "scenario_id": base_id,
                                "placed_scenario_id": scenario["id"],
                                "split": split,
                                "distance_m": placement["distance_m"],
                                "zone_id": placement["zone_id"],
                            })
                        all_component_rows.extend(components)

                        synthetic_returns = int(truth["synthetic_returns"])
                        if synthetic_returns <= 0:
                            visibility_failures.append(row_id)
                        labels_path = Path("point_labels") / f"{row_id}.json"
                        truth_path = Path("ground_truth") / f"{row_id}.json"
                        components_path = Path("component_rows") / f"{row_id}.json"
                        baseline_path = Path("baseline_candidate_baseline_v2") / f"{row_id}.json"
                        write_json(args.output / labels_path, label_sidecar(labels, scenario))
                        write_json(args.output / truth_path, truth)
                        write_json(args.output / components_path, components)
                        baseline_payload = {
                            "row_id": row_id,
                            "status": result.get("status"),
                            "reason": result.get("reason"),
                            "noise_filter_mode": result.get("noise_filter_mode"),
                            "core_count": result.get("core_count"),
                            "reportable_core_count": result.get("reportable_core_count"),
                            "model_reportable_core_count": result.get("model_reportable_core_count"),
                            "component_summary": component_summary,
                            "processing_ms": result.get("processing_ms"),
                            "legacy_processing_ms": result.get("legacy_processing_ms"),
                            "model_processing_ms": result.get("model_processing_ms"),
                        }
                        write_json(args.output / baseline_path, baseline_payload)

                        split_counts[split] += 1
                        for key in ("positive_components", "model_tp_components", "model_fn_components",
                                    "model_fp_components"):
                            baseline_totals[key] += component_summary[key]
                            slice_metrics[base_id][key] += component_summary[key]
                        baseline_totals["unknown_rows"] += int(component_summary["unknown"])
                        slice_metrics[base_id]["rows"] += 1
                        slice_metrics[base_id]["unknown_rows"] += int(component_summary["unknown"])

                        manifest_rows.append({
                            "dataset_version": args.dataset_version,
                            "row_id": row_id,
                            "source_run_id": source_id,
                            "source_frame_index": frame_index,
                            "background_group_id": f"{source_id}:frame:{frame_index:04d}",
                            "seed_group_id": f"{source_id}:frame:{frame_index:04d}",
                            "source_frame": record["source_frame"],
                            "target_from_source": config["target_from_source"],
                            "bag_offset_seconds": record["bag_offset_seconds"],
                            "header_timestamp_ns": record["header_timestamp_ns"],
                            "source_point_order": "ArchiveBagFrames usable finite non-zero XYZ order",
                            "source_points": int(source_points.shape[0]),
                            "scenario_id": base_id,
                            "placed_scenario_id": scenario["id"],
                            "placement": placement,
                            "distance_band_m": placement["distance_m"],
                            "zone_id": placement["zone_id"],
                            "low_thin_probe": base_id in LOW_THIN_SCENARIOS,
                            "split": split,
                            "split_policy": args.split_policy,
                            "config_sha256": config_sha256,
                            "point_labels": str(labels_path).replace("\\", "/"),
                            "ground_truth": str(truth_path).replace("\\", "/"),
                            "component_rows": str(components_path).replace("\\", "/"),
                            "baseline_candidate_baseline_v2": str(baseline_path).replace("\\", "/"),
                            "synthetic_returns": synthetic_returns,
                            "component_count": component_summary["core_component_count"],
                            "positive_component_count": component_summary["positive_components"],
                            "candidate_baseline_v2_tp_components": component_summary["model_tp_components"],
                            "candidate_baseline_v2_fn_components": component_summary["model_fn_components"],
                            "candidate_baseline_v2_fp_components": component_summary["model_fp_components"],
                            "visibility_status": "OBSERVED" if synthetic_returns > 0 else "NO_SYNTHETIC_RETURNS",
                            "baseline_status": component_summary["status"],
                        })
            finally:
                source.close()
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    split_manifest = {
        "format": "synthetic_obstacles_v1_split_manifest",
        "dataset_version": args.dataset_version,
        "policy": args.split_policy,
        "rules": split_policy_rules(args.split_policy),
        "split_counts": dict(split_counts),
    }
    generation_summary = {
        "format": "synthetic_obstacles_v1_seeded_splits",
        "scope": "DATASET_LAYER_NO_TRAINING_NO_REAL_RECALL_CLAIM",
        "dataset_version": args.dataset_version,
        "split_policy": args.split_policy,
        "source_windows": [
            {"source_id": source_id, "first": first, "count": count}
            for source_id, first, count in source_windows
        ],
        "scenarios": scenario_ids,
        "distances_m": distances,
        "zones": zones,
        "placements_per_frame": len(placements),
        "manifest_rows": len(manifest_rows),
        "component_rows": len(all_component_rows),
        "split_counts": dict(split_counts),
        "visibility_failures": visibility_failures,
        "baseline_candidate_baseline_v2_component_metrics": dict(baseline_totals),
        "scenario_slices": {key: dict(value) for key, value in sorted(slice_metrics.items())},
        "limitations": [
            "uses compact usable XYZ order from ArchiveBagFrames, not full PointCloud2 schema",
            "placement transform shifts synthetic scenario geometry in assumed source coordinates",
            "causal temporal confirmation is not evaluated by this dataset builder",
            "no candidate training and no runtime default change",
            "synthetic results are development probes, not real-world recall evidence",
        ],
    }
    (args.output / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    write_json(args.output / "component_rows.json", all_component_rows)
    write_json(args.output / "split_manifest.json", split_manifest)
    write_json(args.output / "generation_summary.json", generation_summary)
    print(json.dumps({"output": str(args.output), **generation_summary}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
