"""Build a tiny real-frame synthetic recall smoke dataset.

This validates the development synthetic layer on a few real archive frames:
manifest rows, point-label sidecars, component rows, and baseline candidate_baseline_v2
component matching through curve_pipeline_stream_cli.  It is intentionally not
a full dataset build or model-training entry point.
"""
from __future__ import annotations

import argparse
from collections import Counter
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


DEFAULT_SCENARIOS = ("low_box", "cable", "standing_person")
SOURCES = {
    "roundT_doubleT": ("for_hackathon/roundT_doubleT", "for_hackathon"),
    "squareT_platform_squareT_switch": ("for_hackathon/squareT_platform_squareT_switch", "for_hackathon"),
    "doubleT_platform": ("for_hackathon/doubleT_platform", "for_hackathon"),
    "roundT_squareT_pressureGate_squareT": ("for_hackathon/roundT_squareT_pressureGate_squareT", "for_hackathon"),
    "doubleT_obstacle": ("for_hackathon/doubleT_obstacle", "for_hackathon"),
    "roundT_pressureGate_roundT": ("for_hackathon/roundT_pressureGate_roundT", "for_hackathon"),
    "new_data": ("new_data", "new_data"),
}


def raw_xyz(points: np.ndarray) -> bytes:
    return np.ascontiguousarray(points, dtype="<f4").tobytes()


def stream_result(process: subprocess.Popen[bytes], raw: bytes, source_id: str, row_id: str) -> dict:
    try:
        process.stdin.write(struct.pack("<Q", len(raw) // 12))
        process.stdin.write(raw)
        process.stdin.flush()
    except BrokenPipeError as exc:
        stderr = process.stderr.read().decode(errors="replace")[-1000:]
        raise RuntimeError(f"{source_id} {row_id}: stream pipe closed: {stderr}") from exc
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read().decode(errors="replace")[-1000:]
        raise RuntimeError(f"{source_id} {row_id}: stream stopped: {stderr}")
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
        }

    raw = raw_xyz(points)
    core = result.get("core_source_indices", [])
    groups = connected_components(raw, core, 0.25)
    legacy_reportable = set(result.get("reportable_core_source_indices", []))
    model_reportable = set(result.get("model_reportable_core_source_indices", legacy_reportable))
    rows = []
    totals = Counter()
    for component_id, component in enumerate(groups):
        component_set = set(component)
        synthetic_indices = [index for index in component if int(labels[index]) >= 0]
        matched_labels = sorted({int(labels[index]) for index in synthetic_indices})
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
            "matched_object_labels": matched_labels,
            "legacy_reportable": legacy_hit,
            "candidate_baseline_v2_reportable": model_hit,
            "features": component_features(raw, component),
        })
    summary = {
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
    return rows, summary


def label_rows(labels: np.ndarray, scenario: dict) -> list[dict]:
    rows = []
    for index, label in enumerate(labels.tolist()):
        object_id = None
        category = None
        if label >= 0:
            obstacle = scenario["objects"][label]
            object_id = obstacle["id"]
            category = obstacle.get("category", "UNSPECIFIED")
        rows.append({
            "point_index": index,
            "object_label": int(label),
            "object_id": object_id,
            "category": category,
            "synthetic_return": label >= 0,
        })
    return rows


def write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "synthetic_obstacles_development.yaml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stream-cli", default="/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    parser.add_argument("--source", choices=sorted(SOURCES), default="doubleT_obstacle")
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--scenario", action="append", default=[])
    args = parser.parse_args()

    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty output: {args.output}")
    if args.first < 0 or args.count < 1:
        raise ValueError("invalid frame range")

    config = load_synthetic_config(args.config)
    scenarios = {scenario["id"]: scenario for scenario in scenario_catalog(config)}
    scenario_ids = args.scenario or list(DEFAULT_SCENARIOS)
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in scenarios]
    if missing:
        raise ValueError(f"unknown scenario ids: {missing}")

    prefix, archive_name = SOURCES[args.source]
    archive_path = args.root / "dataset" / "for_hackathon" / archive_name
    if not archive_path.exists():
        raise FileNotFoundError(f"missing archive: {archive_path}")

    config_sha256 = hashlib.sha256(args.config.read_bytes()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    for child in ("ground_truth", "point_labels", "component_rows", "baseline_candidate_baseline_v2"):
        (args.output / child).mkdir(exist_ok=True)

    manifest_rows = []
    all_component_rows = []
    baseline_rows = []
    visibility_failures = []
    source = ArchiveBagFrames(archive_path, prefix, args.source)
    process = subprocess.Popen(
        [args.stream_cli, "2.0", "--compare-noise-filters"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        last = min(args.first + args.count - 1, len(source.lookup) - 1)
        for frame_index in range(args.first, last + 1):
            record, raw = source.frame(frame_index)
            if record["source_frame"] != config["source_frame"]:
                raise ValueError(
                    f"SOURCE_FRAME_MISMATCH:{record['source_frame']}!={config['source_frame']}"
                )
            source_points = np.frombuffer(raw, dtype="<f4").reshape(-1, 3).astype(np.float64)
            for scenario_id in scenario_ids:
                scenario = scenarios[scenario_id]
                augmented, labels, truth = raycast_scene(
                    source_points, config, frame_index=frame_index, scenario_id=scenario_id
                )
                row_id = f"{args.source}_frame_{frame_index:04d}_{scenario_id}"
                augmented_raw = raw_xyz(augmented)
                result = stream_result(process, augmented_raw, args.source, row_id)
                if result.get("safety_decision_permitted") is not False:
                    raise ValueError(f"{row_id}: safety contract changed")

                components, component_summary = component_rows(augmented, labels, result)
                for row in components:
                    row.update({
                        "row_id": row_id,
                        "source_id": args.source,
                        "source_frame_index": frame_index,
                        "scenario_id": scenario_id,
                    })
                all_component_rows.extend(components)

                synthetic_returns = int(truth["synthetic_returns"])
                if synthetic_returns <= 0:
                    visibility_failures.append(row_id)
                labels_path = Path("point_labels") / f"{row_id}.json"
                truth_path = Path("ground_truth") / f"{row_id}.json"
                components_path = Path("component_rows") / f"{row_id}.json"
                baseline_path = Path("baseline_candidate_baseline_v2") / f"{row_id}.json"
                write_json(args.output / labels_path, label_rows(labels, scenario))
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
                baseline_rows.append(baseline_payload)

                manifest_rows.append({
                    "dataset_version": "synthetic_obstacles_v1_smoke_real_frames",
                    "row_id": row_id,
                    "source_run_id": args.source,
                    "source_frame_index": frame_index,
                    "source_frame": record["source_frame"],
                    "target_from_source": config["target_from_source"],
                    "bag_offset_seconds": record["bag_offset_seconds"],
                    "header_timestamp_ns": record["header_timestamp_ns"],
                    "source_point_order": "ArchiveBagFrames usable finite non-zero XYZ order",
                    "source_points": int(source_points.shape[0]),
                    "scenario_id": scenario_id,
                    "split": "smoke",
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
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    totals = Counter()
    for row in baseline_rows:
        summary = row["component_summary"]
        totals["unknown_rows"] += int(summary["unknown"])
        totals["positive_components"] += summary["positive_components"]
        totals["model_tp_components"] += summary["model_tp_components"]
        totals["model_fn_components"] += summary["model_fn_components"]
        totals["model_fp_components"] += summary["model_fp_components"]
    summary = {
        "format": "synthetic_obstacles_v1_smoke_real_frames",
        "scope": "REAL_SOURCE_FRAMES_SMALL_SMOKE_NO_TRAINING_NO_RECALL_CLAIM",
        "source": args.source,
        "frame_range_inclusive": [args.first, min(args.first + args.count - 1, len(source.lookup) - 1)],
        "scenarios": scenario_ids,
        "manifest_rows": len(manifest_rows),
        "component_rows": len(all_component_rows),
        "visibility_failures": visibility_failures,
        "baseline_candidate_baseline_v2_component_metrics": dict(totals),
        "limitations": [
            "uses compact usable XYZ order from ArchiveBagFrames, not full PointCloud2 schema",
            "causal temporal confirmation is not evaluated in this tiny non-sequential smoke",
            "synthetic visibility is observed-ray limited and may produce zero-return placements",
            "no full dataset build, no candidate training, no runtime default change",
        ],
    }
    (args.output / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    write_json(args.output / "component_rows.json", all_component_rows)
    write_json(args.output / "generation_summary.json", summary)
    print(json.dumps({"output": str(args.output), **summary}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
