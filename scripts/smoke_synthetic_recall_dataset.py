"""Build a tiny synthetic-recall smoke dataset and component-level metrics.

This is deliberately small and offline.  It validates the manifest/point-label
sidecar shape and synthetic component matching without running a full bag replay
or training candidate models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from collections import Counter

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from synthetic_obstacle_generator import load_synthetic_config, raycast_scene, scenario_catalog  # noqa: E402
from train_noise_classifier import component_features, connected_components  # noqa: E402


DEFAULT_SCENARIOS = ("low_box", "cable", "standing_person")


def primitive_centers(scenario: dict) -> list[np.ndarray]:
    centers: list[np.ndarray] = []
    for obstacle in scenario["objects"]:
        primitives = obstacle.get("parts", [obstacle])
        for primitive in primitives:
            centers.append(np.asarray(primitive["center_xyz"], dtype=np.float64))
    return centers


def source_fixture(scenario: dict, frame_variant: int) -> np.ndarray:
    """Create a tiny source frame with rays through scenario geometry."""
    points = []
    for center in primitive_centers(scenario):
        # Use the same real-ray idea as the generator: a source return behind
        # the requested obstacle gives the synthetic surface a chance to occlude.
        points.append(center * (2.0 + 0.1 * frame_variant))
    points.extend([
        np.asarray([3.0 + frame_variant, -12.0, 0.5], dtype=np.float64),
        np.asarray([0.0, 0.0, 0.0], dtype=np.float64),
    ])
    return np.asarray(points, dtype=np.float64)


def raw_xyz(points: np.ndarray) -> bytes:
    payload = bytearray()
    for point in points.astype(np.float32):
        payload.extend(struct.pack("<fff", float(point[0]), float(point[1]), float(point[2])))
    return bytes(payload)


def component_rows(points: np.ndarray, labels: np.ndarray, radius_m: float) -> list[dict]:
    finite = np.isfinite(points).all(axis=1)
    nonzero = ~(points == 0.0).all(axis=1)
    source_indices = [int(index) for index in np.flatnonzero(finite & nonzero)]
    raw = raw_xyz(points)
    rows = []
    for component_id, component in enumerate(connected_components(raw, source_indices, radius_m)):
        synthetic_indices = [index for index in component if int(labels[index]) >= 0]
        rows.append({
            "component_id": component_id,
            "source_indices": component,
            "point_count": len(component),
            "synthetic_point_count": len(synthetic_indices),
            "matched_object_labels": sorted({int(labels[index]) for index in synthetic_indices}),
            "features": component_features(raw, component),
        })
    return rows


def evaluate_components(rows: list[dict]) -> dict:
    """Smoke oracle: components with synthetic labels are reportable."""
    tp = sum(row["synthetic_point_count"] > 0 for row in rows)
    fp = sum(row["synthetic_point_count"] == 0 and row.get("oracle_reportable", False) for row in rows)
    fn = sum(row["synthetic_point_count"] > 0 and not row.get("oracle_reportable", False) for row in rows)
    tn = sum(row["synthetic_point_count"] == 0 and not row.get("oracle_reportable", False) for row in rows)
    return {"tp_components": tp, "fn_components": fn, "fp_components": fp, "tn_components": tn}


def write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "synthetic_obstacles_development.yaml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--source-frame-count", type=int, default=2)
    parser.add_argument("--connectivity-radius-m", type=float, default=0.25)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty output: {args.output}")
    if args.source_frame_count < 1:
        raise ValueError("--source-frame-count must be positive")
    config = load_synthetic_config(args.config)
    by_id = {scenario["id"]: scenario for scenario in scenario_catalog(config)}
    scenario_ids = args.scenario or list(DEFAULT_SCENARIOS)
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in by_id]
    if missing:
        raise ValueError(f"unknown scenario ids: {missing}")

    config_bytes = args.config.read_bytes()
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "point_labels").mkdir(exist_ok=True)
    (args.output / "ground_truth").mkdir(exist_ok=True)

    manifest_rows = []
    all_components = []
    scenario_counts = Counter()
    visibility_failures = []
    for frame_index in range(args.source_frame_count):
        for scenario_id in scenario_ids:
            scenario = by_id[scenario_id]
            source = source_fixture(scenario, frame_index)
            augmented, labels, truth = raycast_scene(
                source, config, frame_index=frame_index, scenario_id=scenario_id)
            label_rows = []
            for index, label in enumerate(labels.tolist()):
                object_id = None
                category = None
                if label >= 0:
                    obstacle = scenario["objects"][label]
                    object_id = obstacle["id"]
                    category = obstacle.get("category", "UNSPECIFIED")
                label_rows.append({
                    "point_index": index,
                    "object_label": int(label),
                    "object_id": object_id,
                    "category": category,
                })
            row_id = f"frame_{frame_index:04d}_{scenario_id}"
            labels_path = Path("point_labels") / f"{row_id}.json"
            truth_path = Path("ground_truth") / f"{row_id}.json"
            write_json(args.output / labels_path, label_rows)
            write_json(args.output / truth_path, truth)

            components = component_rows(augmented, labels, args.connectivity_radius_m)
            for component in components:
                component["oracle_reportable"] = component["synthetic_point_count"] > 0
                component["row_id"] = row_id
                component["scenario_id"] = scenario_id
            all_components.extend(components)

            synthetic_returns = int(truth["synthetic_returns"])
            if synthetic_returns <= 0:
                visibility_failures.append(row_id)
            scenario_counts[scenario_id] += 1
            manifest_rows.append({
                "dataset_version": "synthetic_recall_smoke",
                "row_id": row_id,
                "source_run_id": "tiny_source_frame_fixture",
                "source_frame_index": frame_index,
                "source_frame": config["source_frame"],
                "target_from_source": config["target_from_source"],
                "scenario_id": scenario_id,
                "split": "smoke",
                "config_sha256": config_sha256,
                "point_labels": str(labels_path).replace("\\", "/"),
                "ground_truth": str(truth_path).replace("\\", "/"),
                "synthetic_returns": synthetic_returns,
                "component_count": len(components),
                "positive_component_count": sum(component["synthetic_point_count"] > 0 for component in components),
                "visibility_status": "OBSERVED" if synthetic_returns > 0 else "NO_SYNTHETIC_RETURNS",
            })

    metrics = evaluate_components(all_components)
    summary = {
        "format": "synthetic_recall_smoke_v1",
        "scope": "TINY_FIXTURE_NO_REAL_RECALL_CLAIM",
        "source_frame_count": args.source_frame_count,
        "scenarios": scenario_ids,
        "manifest_rows": len(manifest_rows),
        "components": len(all_components),
        "scenario_counts": dict(scenario_counts),
        "visibility_failures": visibility_failures,
        "oracle_component_metrics": metrics,
        "limitations": [
            "tiny source-frame fixtures, not real bag replay",
            "oracle reportable decision only validates synthetic component matching",
            "no model training or runtime default change",
        ],
    }
    manifest_path = args.output / "manifest.jsonl"
    manifest_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    write_json(args.output / "generation_summary.json", summary)
    print(json.dumps({"output": str(args.output), **summary}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
