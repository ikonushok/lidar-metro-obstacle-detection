"""Train and evaluate noise-model candidates on synthetic component rows.

This is a development evaluator for the synthetic dataset layer.  It reads the
component rows produced by build_synthetic_recall_dataset.py, trains candidates
on the frozen train split, calibrates thresholds on calibration, and evaluates
on synthetic_held_out.  It does not change runtime defaults or C++ artifacts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import pickle
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for path in (ROOT / "src", SCRIPTS):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from evaluate_noise_model_candidates import (  # noqa: E402
    CandidateScorer,
    FEATURE_NAMES,
    apply_temporal,
    temporal_rule_description,
    predict_index_tree_probability,
    predict_probability,
    train_candidates,
)


EVALUATED_CANDIDATES = (
    "candidate_baseline_v2",
    "random_forest_lite",
    "random_forest",
    "lightgbm",
    "ensemble_v1",
    "gradient_boosting",
    "decision_tree",
    "tree_depth3",
    "tree_depth5_min10",
)


def balanced_training_rows(component_rows: list[dict], split: str) -> list[dict]:
    rows = []
    for row in component_rows:
        if row.get("split") != split:
            continue
        rows.append({
            "features": row["features"],
            "label": int(row.get("synthetic_point_count", 0)) > 0,
            "source_row_id": row["row_id"],
            "scenario_id": row.get("scenario_id"),
        })
    counts = Counter(row["label"] for row in rows)
    if not counts[True] or not counts[False]:
        raise ValueError(f"training split needs both classes, got {dict(counts)}")
    for row in rows:
        row["weight"] = 0.5 / counts[row["label"]]
    return rows


def event_key(row: dict) -> str:
    return (
        f"{row.get('source_id')}:{row.get('scenario_id')}:"
        f"d{int(row.get('distance_m', -1)):03d}:{row.get('zone_id')}"
    )


def frames_from_components(component_rows: list[dict], split: str) -> list[dict]:
    by_row: dict[str, list[dict]] = defaultdict(list)
    for component in component_rows:
        if component.get("split") == split:
            by_row[component["row_id"]].append(component)
    frames = []
    for index, row_id in enumerate(sorted(by_row)):
        components = sorted(by_row[row_id], key=lambda item: int(item["component_id"]))
        positive_ids = {
            int(component["component_id"])
            for component in components
            if int(component.get("synthetic_point_count", 0)) > 0
        }
        first = components[0]
        frames.append({
            "row_id": row_id,
            "source_id": event_key(first),
            "frame": int(first.get("source_frame_index", index)),
            "bag_offset_seconds": float(index),
            "unknown": False,
            "target": bool(positive_ids),
            "target_component_ids": positive_ids,
            "scenario_id": first.get("scenario_id"),
            "distance_m": first.get("distance_m"),
            "zone_id": first.get("zone_id"),
            "low_thin_probe": first.get("scenario_id") in {
                "low_box", "cable", "pipe_across_track", "shovel", "jacket_bundle", "crowbar"
            },
            "components": [
                {
                    "component_id": int(component["component_id"]),
                    "features": component["features"],
                    "label": int(component.get("synthetic_point_count", 0)) > 0,
                    "synthetic_point_count": int(component.get("synthetic_point_count", 0)),
                }
                for component in components
            ],
        })
    frames.sort(key=lambda item: (item["source_id"], item["frame"], item["row_id"]))
    for index, frame in enumerate(frames):
        frame["bag_offset_seconds"] = float(index)
    return frames


def load_forest_lite(path: Path) -> CandidateScorer:
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("format") != "lidar-component-noise-forest-lite-v1":
        raise ValueError(f"unexpected candidate_baseline_v2 format: {model.get('format')}")
    trees = model["trees"]
    return CandidateScorer(
        "candidate_baseline_v2",
        lambda features: sum(predict_index_tree_probability(tree, features) for tree in trees) / len(trees),
        portable_model=model,
    )


def threshold_grid(scores: list[float], steps: int) -> list[float]:
    values = {0.5}
    if steps > 0:
        values.update(index / steps for index in range(1, steps))
    if scores:
        ordered = sorted(scores)
        for index in range(1, min(steps, len(ordered))):
            position = round((len(ordered) - 1) * index / steps)
            values.add(ordered[position])
    return sorted(value for value in values if 0.0 <= value <= 1.0)


def score_frames(frames: list[dict], scorer: CandidateScorer, threshold: float,
                 temporal_mode: str) -> list[dict]:
    refs = []
    features = []
    for frame_index, frame in enumerate(frames):
        for component in frame["components"]:
            refs.append((frame_index, component))
            features.append(component["features"])
    scores = scorer.score_many(features)
    rows = []
    for frame in frames:
        rows.append({
            "source_id": frame["source_id"],
            "row_id": frame["row_id"],
            "frame": frame["frame"],
            "scenario_id": frame["scenario_id"],
            "distance_m": frame["distance_m"],
            "zone_id": frame["zone_id"],
            "low_thin_probe": frame["low_thin_probe"],
            "unknown": False,
            "target": frame["target"],
            "raw_alarm": False,
            "target_hit": False,
            "false_components": 0,
            "positive_components": len(frame["target_component_ids"]),
        })
    for (frame_index, component), score in zip(refs, scores):
        if score < threshold:
            continue
        row = rows[frame_index]
        row["raw_alarm"] = True
        if component["component_id"] in frames[frame_index]["target_component_ids"]:
            row["target_hit"] = True
        else:
            row["false_components"] += 1
    apply_temporal(rows, "raw_alarm", "temporal_alarm", temporal_mode)
    for row in rows:
        row["temporal_target_hit"] = row["temporal_alarm"] and row["target_hit"]
        row["temporal_false_components"] = row["false_components"] if row["temporal_alarm"] else 0
    return rows


def summarize(rows: list[dict]) -> dict:
    return {
        "frames": len(rows),
        "positive_frames": sum(row["target"] for row in rows),
        "raw": {
            "tp_frames": sum(row["target"] and row["target_hit"] for row in rows),
            "fn_frames": sum(row["target"] and not row["target_hit"] for row in rows),
            "fp_frames": sum(not row["target"] and row["raw_alarm"] for row in rows),
            "tn_frames": sum(not row["target"] and not row["raw_alarm"] for row in rows),
            "fp_components": sum(row["false_components"] for row in rows),
        },
        "temporal": {
            "tp_frames": sum(row["target"] and row["temporal_target_hit"] for row in rows),
            "fn_frames": sum(row["target"] and not row["temporal_target_hit"] for row in rows),
            "fp_frames": sum(not row["target"] and row["temporal_alarm"] for row in rows),
            "tn_frames": sum(not row["target"] and not row["temporal_alarm"] for row in rows),
            "fp_components": sum(row["temporal_false_components"] for row in rows),
        },
    }


def summarize_slices(rows: list[dict]) -> dict:
    slices = {}
    for key_name in ("scenario_id", "zone_id", "distance_m"):
        by_key: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_key[str(row[key_name])].append(row)
        slices[key_name] = {key: summarize(value) for key, value in sorted(by_key.items())}
    low_thin = [row for row in rows if row["low_thin_probe"]]
    regular = [row for row in rows if not row["low_thin_probe"]]
    slices["probe_family"] = {
        "low_thin": summarize(low_thin),
        "regular": summarize(regular),
    }
    return slices


def calibrate(frames: list[dict], scorer: CandidateScorer, steps: int,
              temporal_mode: str) -> dict:
    all_scores = []
    for frame in frames:
        all_scores.extend(scorer.score_many([component["features"] for component in frame["components"]]))
    best = None
    for threshold in threshold_grid(all_scores, steps):
        rows = score_frames(frames, scorer, threshold, temporal_mode)
        summary = summarize(rows)
        candidate = {
            "threshold": threshold,
            "raw": summary["raw"],
            "temporal": summary["temporal"],
        }
        key = (
            candidate["temporal"]["fn_frames"],
            candidate["temporal"]["fp_frames"],
            candidate["raw"]["fn_frames"],
            candidate["raw"]["fp_frames"],
            -threshold,
        )
        if best is None or key < best["selection_key"]:
            best = {**candidate, "selection_key": key}
    assert best is not None
    best.pop("selection_key")
    return best


def evaluate(name: str, scorer: CandidateScorer, frames: list[dict], threshold: float,
             temporal_mode: str) -> dict:
    started = time.perf_counter_ns()
    rows = score_frames(frames, scorer, threshold, temporal_mode)
    summary = summarize(rows)
    summary.update({
        "candidate": name,
        "threshold": threshold,
        "evaluation_ms": (time.perf_counter_ns() - started) / 1e6,
        "slices": summarize_slices(rows),
    })
    return summary


def save_models(candidates: dict[str, CandidateScorer], thresholds: dict[str, float],
                output: Path, summary: dict) -> list[dict]:
    model_dir = output / "trained_models"
    model_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, candidate in candidates.items():
        if candidate.model is not None:
            path = model_dir / f"{name}.pkl"
            with path.open("wb") as handle:
                pickle.dump(candidate.model, handle)
            saved.append({"candidate": name, "path": str(path), "format": "pickle"})
        if candidate.portable_model is not None and name != "candidate_baseline_v2":
            path = model_dir / f"{name}.json"
            payload = {
                **candidate.portable_model,
                "threshold": thresholds[name],
                "training": summary["training"],
                "calibration": summary["calibration"]["results"].get(name),
                "synthetic_evaluation": next(
                    (result for result in summary["results"] if result["candidate"] == name),
                    None,
                ),
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            saved.append({"candidate": name, "path": str(path), "format": payload["format"]})
    (model_dir / "manifest.json").write_text(
        json.dumps(saved, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component-rows", type=Path, required=True)
    parser.add_argument("--candidate-baseline-v2", type=Path,
                        default=ROOT / "models" / "noise_classifier_candidate_baseline_v2.json")
    parser.add_argument("--model-v1", type=Path,
                        default=ROOT / "models" / "noise_classifier_doubleT_obstacle_v1.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold-steps", type=int, default=31)
    parser.add_argument("--seed", type=int, default=20260924)
    parser.add_argument("--temporal-mode", choices=["causal_runtime", "legacy_adjacent"],
                        default="causal_runtime")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty output: {args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    component_rows = json.loads(args.component_rows.read_text(encoding="utf-8"))
    train_rows = balanced_training_rows(component_rows, "train")
    calibration_frames = frames_from_components(component_rows, "calibration")
    held_out_frames = frames_from_components(component_rows, "synthetic_held_out")
    if not calibration_frames or not held_out_frames:
        raise ValueError("synthetic dataset must contain calibration and synthetic_held_out splits")

    frozen_tree = json.loads(args.model_v1.read_text(encoding="utf-8"))["tree"]
    candidates, skipped = train_candidates(train_rows, frozen_tree, args.seed)
    candidates = {name: candidate for name, candidate in candidates.items() if name in EVALUATED_CANDIDATES}
    candidates["candidate_baseline_v2"] = load_forest_lite(args.candidate_baseline_v2)

    thresholds = {}
    calibration_results = {}
    for name, scorer in candidates.items():
        if name == "candidate_baseline_v2":
            threshold = scorer.portable_model.get("threshold", 0.5)
            calibration_results[name] = {"threshold": threshold, "fixed_baseline": True}
        else:
            calibration_results[name] = calibrate(calibration_frames, scorer, args.threshold_steps,
                                                  args.temporal_mode)
            threshold = calibration_results[name]["threshold"]
        thresholds[name] = threshold

    results = [
        evaluate(name, candidates[name], held_out_frames, thresholds[name], args.temporal_mode)
        for name in EVALUATED_CANDIDATES
        if name in candidates
    ]
    baseline = next((result for result in results if result["candidate"] == "candidate_baseline_v2"), None)
    if baseline is not None:
        baseline_key = (
            baseline["temporal"]["fn_frames"],
            baseline["temporal"]["fp_frames"],
            baseline["raw"]["fn_frames"],
            baseline["raw"]["fp_frames"],
        )
        for result in results:
            result["delta_vs_candidate_baseline_v2"] = {
                "temporal_fn_frames": result["temporal"]["fn_frames"] - baseline["temporal"]["fn_frames"],
                "temporal_fp_frames": result["temporal"]["fp_frames"] - baseline["temporal"]["fp_frames"],
                "raw_fn_frames": result["raw"]["fn_frames"] - baseline["raw"]["fn_frames"],
                "raw_fp_frames": result["raw"]["fp_frames"] - baseline["raw"]["fp_frames"],
            }
            result["beats_candidate_baseline_v2_gate"] = (
                (
                    result["temporal"]["fn_frames"],
                    result["temporal"]["fp_frames"],
                    result["raw"]["fn_frames"],
                    result["raw"]["fp_frames"],
                ) < baseline_key
            )

    summary = {
        "scope": "SYNTHETIC_COMPONENT_CANDIDATE_SCREENING_NO_RUNTIME_CHANGE",
        "component_rows": str(args.component_rows),
        "train_split": "train",
        "calibration_split": "calibration",
        "evaluation_split": "synthetic_held_out",
        "temporal_mode": args.temporal_mode,
        "temporal_rule": temporal_rule_description(args.temporal_mode),
        "training": {
            "component_count": len(train_rows),
            "class_counts": dict(Counter(row["label"] for row in train_rows)),
            "features": list(FEATURE_NAMES),
            "seed": args.seed,
        },
        "calibration": {
            "threshold_steps": args.threshold_steps,
            "frame_count": len(calibration_frames),
            "results": calibration_results,
        },
        "skipped_candidates": skipped,
        "held_out_frame_count": len(held_out_frames),
        "results": results,
    }
    summary["saved_models"] = save_models(candidates, thresholds, args.output, summary)
    summary["ranking"] = sorted(
        [
            {
                "candidate": result["candidate"],
                "temporal_fn_frames": result["temporal"]["fn_frames"],
                "temporal_fp_frames": result["temporal"]["fp_frames"],
                "raw_fn_frames": result["raw"]["fn_frames"],
                "raw_fp_frames": result["raw"]["fp_frames"],
            }
            for result in results
        ],
        key=lambda item: (
            item["temporal_fn_frames"], item["temporal_fp_frames"],
            item["raw_fn_frames"], item["raw_fp_frames"],
        ),
    )
    path = args.output / "synthetic_noise_model_candidates.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "ranking": summary["ranking"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
