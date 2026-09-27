"""Evaluate lightweight noise-model candidates with the same temporal filter.

The target metric is always candidate + temporal. Raw per-frame alarms are kept
only as diagnostics and are not the replacement criterion for candidate_baseline_v2.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import pickle
from pathlib import Path
import random
import struct
import subprocess
import time
from typing import Callable

from archive_bag_frames import ArchiveBagFrames
from train_noise_classifier import (
    FEATURE_NAMES,
    component_features,
    connected_components,
    gini,
    predict_probability,
)


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


class CandidateScorer:
    def __init__(self, name: str, score_one: Callable[[list[float]], float],
                 model=None, members: list["CandidateScorer"] | None = None,
                 portable_model: dict | None = None):
        self.name = name
        self._score_one = score_one
        self.model = model
        self.members = members or []
        self.portable_model = portable_model

    def __call__(self, features: list[float]) -> float:
        return self._score_one(features)

    def score_many(self, feature_rows: list[list[float]]) -> list[float]:
        if not feature_rows:
            return []
        if self.members:
            member_scores = [member.score_many(feature_rows) for member in self.members]
            return [sum(scores[index] for scores in member_scores) / len(member_scores)
                    for index in range(len(feature_rows))]
        if self.model is not None:
            if hasattr(self.model, "predict_proba"):
                return [float(value[1]) for value in self.model.predict_proba(feature_rows)]
            return [float(value) for value in self.model.predict(feature_rows)]
        return [self._score_one(features) for features in feature_rows]


def source_archive(root: Path, archive_name: str) -> Path:
    return root / "dataset/for_hackathon" / archive_name


def stream_result(process: subprocess.Popen[bytes], raw: bytes, source_id: str, frame: int) -> dict:
    try:
        process.stdin.write(struct.pack("<Q", len(raw) // 12))
        process.stdin.write(raw)
        process.stdin.flush()
    except BrokenPipeError as exc:
        stderr = process.stderr.read().decode(errors="replace")[-1000:]
        raise RuntimeError(f"{source_id} frame {frame}: C++ stream pipe closed: {stderr}") from exc
    line = process.stdout.readline()
    if not line:
        raise RuntimeError(
            f"{source_id} frame {frame}: C++ stream stopped: "
            + process.stderr.read().decode(errors="replace")[-1000:]
        )
    return json.loads(line)


def component_frame_rows(raw: bytes, result: dict, frame: int, source_id: str) -> tuple[list[dict], dict]:
    target = source_id == "doubleT_obstacle" and 13 <= frame <= 64
    if result["status"] == "UNKNOWN":
        return [], {
            "unknown": True,
            "target": target,
            "unknown_reason": result.get("reason", "<missing>"),
            "curve_axis_status": result.get("curve_axis_status", "<missing>"),
            "rail_axis_failure_diagnostics": result.get("rail_axis_failure_diagnostics"),
        }
    groups = connected_components(raw, result["core_source_indices"], 0.25)
    reportable = set(result["reportable_core_source_indices"])
    legacy_groups = [group for group in groups if set(group) <= reportable]
    target_group = max(legacy_groups, key=len) if target and legacy_groups else None
    target_key = tuple(target_group) if target_group is not None else None
    rows = []
    for index, group in enumerate(groups):
        key = tuple(group)
        rows.append({
            "component_id": index,
            "component_key": key,
            "features": component_features(raw, group),
            "label": key == target_key,
        })
    frame_row = {
        "unknown": False,
        "target": target,
        "target_component_id": None if target_key is None else next(
            row["component_id"] for row in rows if row["component_key"] == target_key
        ),
        "component_count": len(rows),
    }
    return rows, frame_row


def load_frames(root: Path, stream_cli: str, stream_mode: str, compare_noise_filters: bool,
                selected_sources: set[str] | None,
                first: int, last: int | None, duration_seconds: float | None) -> list[dict]:
    frames = []
    for source_id, prefix, archive_name in SOURCES:
        if selected_sources is not None and source_id not in selected_sources:
            continue
        source = ArchiveBagFrames(source_archive(root, archive_name), prefix, source_id)
        command = [stream_cli, stream_mode]
        if compare_noise_filters:
            command.append("--compare-noise-filters")
        process = subprocess.Popen(command,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            final = len(source.lookup) - 1 if last is None else min(last, len(source.lookup) - 1)
            first_offset = None
            for frame in range(first, final + 1):
                record, raw = source.frame(frame)
                if first_offset is None:
                    first_offset = record["bag_offset_seconds"]
                if duration_seconds is not None and frames and record["bag_offset_seconds"] - first_offset > duration_seconds:
                    break
                result = stream_result(process, raw, source_id, frame)
                if result.get("safety_decision_permitted") is not False:
                    raise ValueError(f"{source_id} frame {frame}: safety contract changed")
                components, frame_row = component_frame_rows(raw, result, frame, source_id)
                frame_row.update({
                    "source_id": source_id,
                    "frame": frame,
                    "bag_offset_seconds": record["bag_offset_seconds"],
                    "components": components,
                })
                frames.append(frame_row)
                if frame % 100 == 0:
                    print(f"{source_id}: {frame + 1}/{len(source.lookup)}", flush=True)
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
    return frames


def apply_balanced_weights(rows: list[dict]) -> None:
    counts = Counter(row["label"] for row in rows)
    if not counts[True] or not counts[False]:
        raise ValueError(f"training needs both classes, got {dict(counts)}")
    for row in rows:
        row["weight"] = 0.5 / counts[row["label"]]


def annotate_legacy_tree_v1_temporal(frames: list[dict], frozen_tree: dict, threshold: float,
                                     temporal_mode: str) -> None:
    rows = []
    for frame in frames:
        row = {
            "source_id": frame["source_id"],
            "frame": frame["frame"],
            "unknown": frame["unknown"],
            "raw_alarm": False,
        }
        if not frame["unknown"]:
            for component in frame["components"]:
                score = predict_probability(frozen_tree, component["features"])
                component["legacy_tree_v1_score"] = score
                row["raw_alarm"] = row["raw_alarm"] or score >= threshold
        rows.append(row)
    apply_temporal(rows, "raw_alarm", "temporal_alarm", temporal_mode)
    for frame, row in zip(frames, rows):
        frame["legacy_tree_v1_temporal_alarm"] = row["temporal_alarm"]


def load_forest_lite(path: Path) -> CandidateScorer:
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("format") != "lidar-component-noise-forest-lite-v1":
        raise ValueError(f"unexpected forest-lite format: {model.get('format')}")
    trees = model["trees"]
    return CandidateScorer(
        "candidate_baseline_v2",
        lambda features: sum(predict_index_tree_probability(tree, features) for tree in trees) / len(trees),
        portable_model=model,
    )


def synthetic_training_rows(component_rows_path: Path, split: str) -> tuple[list[dict], dict]:
    component_rows = json.loads(component_rows_path.read_text(encoding="utf-8"))
    rows = []
    skipped_splits = Counter()
    for row in component_rows:
        row_split = row.get("split")
        if row_split != split:
            skipped_splits[row_split] += 1
            continue
        rows.append({
            "features": row["features"],
            "label": int(row.get("synthetic_point_count", 0)) > 0,
            "source_id": row.get("source_id", "synthetic"),
            "frame": row.get("source_frame_index", -1),
            "component_id": row.get("component_id", -1),
            "training_role": (
                "synthetic_positive"
                if int(row.get("synthetic_point_count", 0)) > 0
                else "synthetic_negative"
            ),
            "synthetic_row_id": row.get("row_id"),
            "synthetic_scenario_id": row.get("scenario_id"),
            "synthetic_distance_m": row.get("distance_m"),
            "synthetic_zone_id": row.get("zone_id"),
        })
    counts = Counter(row["label"] for row in rows)
    if not counts[True]:
        raise ValueError(f"{component_rows_path}: synthetic split {split!r} has no positive components")
    if not counts[False]:
        raise ValueError(f"{component_rows_path}: synthetic split {split!r} has no negative components")
    return rows, {
        "path": str(component_rows_path),
        "split": split,
        "component_count": len(rows),
        "class_counts": {str(key): value for key, value in counts.items()},
        "rows_by_role": dict(Counter(row["training_role"] for row in rows)),
        "skipped_splits": {str(key): value for key, value in skipped_splits.items()},
    }


def training_rows(frames: list[dict], train_sources: set[str]) -> tuple[list[dict], dict]:
    rows = []
    for frame in frames:
        if frame["source_id"] not in train_sources or frame["unknown"]:
            continue
        for component in frame["components"]:
            rows.append({
                "features": component["features"],
                "label": component["label"],
                "source_id": frame["source_id"],
                "frame": frame["frame"],
                "component_id": component["component_id"],
                "training_role": "positive" if component["label"] else "regular_negative",
            })
    apply_balanced_weights(rows)
    return rows, {"mode": "current", "rows_by_role": dict(Counter(row["training_role"] for row in rows))}


def hard_negative_training_rows(frames: list[dict], train_sources: set[str], hard_negative_sources: set[str],
                                regular_negative_ratio: int, seed: int,
                                hard_negative_max_duration_seconds: float | None) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    allowed_sources = train_sources | hard_negative_sources
    first_offsets: dict[str, float] = {}
    for frame in frames:
        first_offsets.setdefault(frame["source_id"], frame["bag_offset_seconds"])
    positives: list[dict] = []
    hard_negatives: list[dict] = []
    regular_pool: list[dict] = []
    hard_negative_keys = set()
    for frame in frames:
        if frame["source_id"] not in allowed_sources or frame["unknown"]:
            continue
        for component in frame["components"]:
            row = {
                "features": component["features"],
                "label": component["label"],
                "source_id": frame["source_id"],
                "frame": frame["frame"],
                "component_id": component["component_id"],
            }
            if component["label"] and frame["source_id"] in train_sources:
                positives.append({**row, "training_role": "positive"})
            elif not component["label"]:
                key = (frame["source_id"], frame["frame"], component["component_id"])
                within_hard_negative_window = True
                if hard_negative_max_duration_seconds is not None and frame["source_id"] in hard_negative_sources:
                    within_hard_negative_window = (
                        frame["bag_offset_seconds"] - first_offsets[frame["source_id"]]
                        < hard_negative_max_duration_seconds
                    )
                is_hard = (
                    frame["source_id"] in hard_negative_sources
                    and within_hard_negative_window
                    and frame.get("legacy_tree_v1_temporal_alarm")
                    and component.get("legacy_tree_v1_score", 0.0) >= 0.5
                )
                if is_hard:
                    hard_negatives.append({**row, "training_role": "hard_negative"})
                    hard_negative_keys.add(key)
                else:
                    regular_pool.append({**row, "training_role": "regular_negative"})
    if not positives:
        raise ValueError("hard-negative training needs positive examples from --train-source")
    regular_limit = max(0, len(positives) * regular_negative_ratio)
    if len(regular_pool) > regular_limit:
        regular_pool = rng.sample(regular_pool, regular_limit)
    rows = positives + hard_negatives + regular_pool
    apply_balanced_weights(rows)
    summary = {
        "mode": "hard_negative",
        "positive_sources": sorted(train_sources),
        "hard_negative_sources": sorted(hard_negative_sources),
        "hard_negative_max_duration_seconds": hard_negative_max_duration_seconds,
        "regular_negative_ratio": regular_negative_ratio,
        "hard_negative_key_count": len(hard_negative_keys),
        "rows_by_role": dict(Counter(row["training_role"] for row in rows)),
    }
    return rows, summary


def make_tree_for_features(rows: list[dict], feature_indices: tuple[int, ...],
                           depth: int, max_depth: int, min_leaf: int) -> dict:
    positive = sum(row["weight"] for row in rows if row["label"])
    negative = sum(row["weight"] for row in rows if not row["label"])
    node = {"positive_weight": positive, "negative_weight": negative}
    if depth >= max_depth or len(rows) < 2 * min_leaf or not positive or not negative:
        return node
    parent_gini = gini(positive, negative)
    best = None
    for feature in feature_indices:
        values = sorted({row["features"][feature] for row in rows})
        if len(values) < 2:
            continue
        positions = sorted({min(len(values) - 2, round((len(values) - 1) * part / 32))
                            for part in range(1, 32)})
        for position in positions:
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
            gain = parent_gini - (
                (left_positive + left_negative) / total * gini(left_positive, left_negative)
                + (right_positive + right_negative) / total * gini(right_positive, right_negative)
            )
            if best is None or gain > best[0]:
                best = gain, feature, threshold, left, right
    if best is None or best[0] <= 1e-9:
        return node
    _, feature, threshold, left, right = best
    node.update({
        "feature": FEATURE_NAMES[feature],
        "feature_index": feature,
        "threshold": threshold,
        "left": make_tree_for_features(left, feature_indices, depth + 1, max_depth, min_leaf),
        "right": make_tree_for_features(right, feature_indices, depth + 1, max_depth, min_leaf),
    })
    return node


def predict_index_tree_probability(tree: dict, features: list[float]) -> float:
    node = tree
    while "feature_index" in node:
        node = node["left"] if features[node["feature_index"]] <= node["threshold"] else node["right"]
    total = node["positive_weight"] + node["negative_weight"]
    return 0.0 if not total else node["positive_weight"] / total


def strip_runtime_tree(tree: dict) -> dict:
    node = {
        "positive_weight": tree["positive_weight"],
        "negative_weight": tree["negative_weight"],
    }
    if "feature_index" in tree:
        node.update({
            "feature": tree["feature"],
            "feature_index": tree["feature_index"],
            "threshold": tree["threshold"],
            "left": strip_runtime_tree(tree["left"]),
            "right": strip_runtime_tree(tree["right"]),
        })
    return node


def stratified_sample(rows: list[dict], rng: random.Random, negative_ratio: int) -> list[dict]:
    positives = [row for row in rows if row["label"]]
    negatives = [row for row in rows if not row["label"]]
    sample = [rng.choice(positives) for _ in range(len(positives))]
    sample.extend(rng.choice(negatives) for _ in range(min(len(negatives), len(positives) * negative_ratio)))
    counts = Counter(row["label"] for row in sample)
    weighted = [dict(row) for row in sample]
    for row in weighted:
        row["weight"] = 0.5 / counts[row["label"]]
    return weighted


def train_candidates(rows: list[dict], frozen_tree: dict, seed: int) -> tuple[
        dict[str, CandidateScorer], list[dict]]:
    started = time.perf_counter()
    print(f"TRAIN start components={len(rows)} seed={seed}", flush=True)
    rng = random.Random(seed)
    all_features = tuple(range(len(FEATURE_NAMES)))
    print("TRAIN candidate=decision_tree/tree_depth3/tree_depth5_min10 start", flush=True)
    decision_tree = make_tree_for_features(rows, all_features, 0, 4, 5)
    tree_depth3 = make_tree_for_features(rows, all_features, 0, 3, 5)
    tree_depth5 = make_tree_for_features(rows, all_features, 0, 5, 10)
    print("TRAIN candidate=random_forest_lite start", flush=True)
    forest_lite = []
    for _ in range(17):
        feature_count = rng.randint(3, len(FEATURE_NAMES))
        features = tuple(sorted(rng.sample(all_features, feature_count)))
        forest_lite.append(make_tree_for_features(stratified_sample(rows, rng, 20), features, 0, 4, 5))

    forest_lite_model = {
        "format": "lidar-component-noise-forest-lite-v1",
        "name": "candidate_baseline_v2",
        "purpose": "OFFLINE_COMPONENT_CLASSIFICATION_NOT_A_SAFETY_OR_CLEAR_DECISION",
        "features": list(FEATURE_NAMES),
        "aggregation": "mean_tree_probability",
        "trees": [strip_runtime_tree(tree) for tree in forest_lite],
        "training_parameters": {
            "candidate": "random_forest_lite",
            "seed": seed,
            "tree_count": len(forest_lite),
            "max_depth": 4,
            "min_leaf": 5,
            "feature_subset_size": "random randint(3, feature_count) per tree",
            "bootstrap": "stratified positive bootstrap plus sampled negatives",
            "negative_ratio": 20,
        },
        "limitations": [
            "MODEL_NEGATIVE_DOES_NOT_MEAN_CLEAR",
            "UNKNOWN_REMAINS_UPSTREAM_STATUS_NOT_MODEL_CLEAR",
            "DEVELOPMENT_CANDIDATE_UNTIL_CPP_PARITY_AND_SYNTHETIC_RECALL_CHECKS_PASS",
        ],
    }

    candidates = {
        "legacy_tree_v1": CandidateScorer("legacy_tree_v1", lambda features: predict_probability(frozen_tree, features)),
        "decision_tree": CandidateScorer(
            "decision_tree", lambda features: predict_index_tree_probability(decision_tree, features)),
        "tree_depth3": CandidateScorer(
            "tree_depth3", lambda features: predict_index_tree_probability(tree_depth3, features)),
        "tree_depth5_min10": CandidateScorer(
            "tree_depth5_min10", lambda features: predict_index_tree_probability(tree_depth5, features)),
        "random_forest_lite": CandidateScorer("random_forest_lite", lambda features: sum(
            predict_index_tree_probability(tree, features) for tree in forest_lite
        ) / len(forest_lite), portable_model=forest_lite_model),
    }
    skipped: list[dict] = []
    ensemble_members = ["decision_tree", "random_forest_lite"]

    feature_matrix = [row["features"] for row in rows]
    labels = [row["label"] for row in rows]
    weights = [row["weight"] for row in rows]
    try:
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
        sklearn_available = True
    except ImportError as error:
        sklearn_available = False
        skipped.extend([
            {"candidate": "random_forest", "reason": f"sklearn unavailable: {error}"},
            {"candidate": "gradient_boosting", "reason": f"sklearn unavailable: {error}"},
        ])
    if sklearn_available:
        model_started = time.perf_counter()
        print("TRAIN candidate=random_forest start", flush=True)
        random_forest = RandomForestClassifier(
            n_estimators=64, max_depth=5, min_samples_leaf=5,
            class_weight="balanced_subsample", random_state=seed, n_jobs=1,
        )
        random_forest.fit(feature_matrix, labels)
        candidates["random_forest"] = CandidateScorer(
            "random_forest", lambda features, model=random_forest: float(model.predict_proba([features])[0][1]),
            model=random_forest)
        ensemble_members.append("random_forest")
        print(f"TRAIN candidate=random_forest done seconds={time.perf_counter() - model_started:.3f}", flush=True)

        model_started = time.perf_counter()
        print("TRAIN candidate=gradient_boosting start", flush=True)
        gradient_boosting = GradientBoostingClassifier(
            n_estimators=64, max_depth=3, min_samples_leaf=5,
            learning_rate=0.05, random_state=seed,
        )
        gradient_boosting.fit(feature_matrix, labels, sample_weight=weights)
        candidates["gradient_boosting"] = CandidateScorer(
            "gradient_boosting",
            lambda features, model=gradient_boosting: float(model.predict_proba([features])[0][1]),
            model=gradient_boosting)
        ensemble_members.append("gradient_boosting")
        print(f"TRAIN candidate=gradient_boosting done seconds={time.perf_counter() - model_started:.3f}", flush=True)

    try:
        from lightgbm import LGBMClassifier
        model_started = time.perf_counter()
        print("TRAIN candidate=lightgbm start", flush=True)
        lightgbm = LGBMClassifier(
            n_estimators=64, max_depth=4, min_child_samples=5,
            learning_rate=0.05, class_weight="balanced", random_state=seed,
            verbosity=-1,
        )
        lightgbm.fit(feature_matrix, labels)
        candidates["lightgbm"] = CandidateScorer(
            "lightgbm", lambda features, model=lightgbm: float(model.predict_proba([features])[0][1]),
            model=lightgbm)
        ensemble_members.append("lightgbm")
        print(f"TRAIN candidate=lightgbm done seconds={time.perf_counter() - model_started:.3f}", flush=True)
    except ImportError as error:
        skipped.append({"candidate": "lightgbm", "reason": f"lightgbm unavailable: {error}"})

    candidates["ensemble_v1"] = CandidateScorer(
        "ensemble_v1",
        lambda features: sum(candidates[name](features) for name in ensemble_members) / len(ensemble_members),
        members=[candidates[name] for name in ensemble_members])
    print(f"TRAIN done candidates={list(candidates)} seconds={time.perf_counter() - started:.3f}", flush=True)
    return candidates, skipped


def temporal_rule_description(temporal_mode: str) -> str:
    if temporal_mode == "causal_runtime":
        return (
            "causal runtime-style confirmation: current alarm and at least one "
            "previous consecutive alarm in the same source; UNKNOWN/source boundary resets state"
        )
    if temporal_mode == "legacy_adjacent":
        return (
            "legacy diagnostic adjacent confirmation: current alarm and at least one "
            "previous or next adjacent alarm in the same source"
        )
    raise ValueError(f"unsupported temporal mode: {temporal_mode}")


def apply_temporal(rows: list[dict], alarm_key: str, output_key: str,
                   temporal_mode: str = "causal_runtime") -> None:
    if temporal_mode == "legacy_adjacent":
        for index, row in enumerate(rows):
            confirmed = False
            if not row["unknown"] and row.get(alarm_key):
                for neighbor_index in (index - 1, index + 1):
                    if 0 <= neighbor_index < len(rows):
                        neighbor = rows[neighbor_index]
                        if (neighbor["source_id"] == row["source_id"] and not neighbor["unknown"]
                                and neighbor.get(alarm_key)):
                            confirmed = True
                            break
            row[output_key] = confirmed
        return
    if temporal_mode != "causal_runtime":
        raise ValueError(f"unsupported temporal mode: {temporal_mode}")
    previous_source_id = None
    previous_alarm = False
    consecutive_alarm_frames = 0
    for row in rows:
        if row["source_id"] != previous_source_id or row["unknown"]:
            previous_alarm = False
            consecutive_alarm_frames = 0
            previous_source_id = row["source_id"]
        if not row["unknown"] and row.get(alarm_key):
            consecutive_alarm_frames = consecutive_alarm_frames + 1 if previous_alarm else 1
        else:
            consecutive_alarm_frames = 0
        row[output_key] = (
            not row["unknown"] and row.get(alarm_key) and consecutive_alarm_frames >= 2
        )
        previous_alarm = not row["unknown"] and bool(row.get(alarm_key))


def score_components(frames: list[dict], name: str, scorer: CandidateScorer) -> tuple[
        list[tuple[int, dict]], list[float]]:
    component_refs: list[tuple[int, dict]] = []
    feature_rows: list[list[float]] = []
    for frame_index, frame in enumerate(frames):
        if frame["unknown"]:
            continue
        for component in frame["components"]:
            component_refs.append((frame_index, component))
            feature_rows.append(component["features"])
    print(f"EVAL candidate={name} start frames={len(frames)} components={len(feature_rows)}", flush=True)
    score_started = time.perf_counter()
    scores = scorer.score_many(feature_rows)
    print(f"EVAL candidate={name} scored components={len(scores)} seconds={time.perf_counter() - score_started:.3f}",
          flush=True)
    return component_refs, scores


def candidate_rows_from_scores(frames: list[dict], component_refs: list[tuple[int, dict]], scores: list[float],
                               threshold: float, temporal_mode: str) -> list[dict]:
    rows = []
    for frame in frames:
        row = {
            "source_id": frame["source_id"],
            "frame": frame["frame"],
            "bag_offset_seconds": frame["bag_offset_seconds"],
            "unknown": frame["unknown"],
            "unknown_reason": frame.get("unknown_reason"),
            "curve_axis_status": frame.get("curve_axis_status"),
            "rail_axis_failure_diagnostics": frame.get("rail_axis_failure_diagnostics"),
            "target": frame["target"],
            "target_hit": False,
            "raw_alarm": False,
            "false_components": 0,
        }
        rows.append(row)
    for (frame_index, component), score in zip(component_refs, scores):
        if score >= threshold:
            row = rows[frame_index]
            frame = frames[frame_index]
            row["raw_alarm"] = True
            if component["component_id"] == frame["target_component_id"]:
                row["target_hit"] = True
            else:
                row["false_components"] += 1
    apply_temporal(rows, "raw_alarm", "temporal_alarm", temporal_mode)
    for row in rows:
        row["temporal_target_hit"] = row["temporal_alarm"] and row["target_hit"]
        row["temporal_false_components"] = row["false_components"] if row["temporal_alarm"] else 0
    return rows


def threshold_grid(scores: list[float], steps: int) -> list[float]:
    fixed = {0.5}
    if steps > 0:
        fixed.update(index / steps for index in range(1, steps))
    if scores:
        sorted_scores = sorted(scores)
        for index in range(1, min(steps, len(sorted_scores))):
            position = round((len(sorted_scores) - 1) * index / steps)
            fixed.add(sorted_scores[position])
    return sorted(value for value in fixed if 0.0 <= value <= 1.0)


def calibrate_threshold(frames: list[dict], name: str, scorer: CandidateScorer, steps: int,
                        temporal_mode: str) -> dict:
    print(f"CALIBRATE candidate={name} start frames={len(frames)} steps={steps}", flush=True)
    component_refs, scores = score_components(frames, name, scorer)
    best: dict | None = None
    duration = (
        frames[-1]["bag_offset_seconds"] - frames[0]["bag_offset_seconds"]
        if len(frames) > 1 else 0.0
    )
    for threshold in threshold_grid(scores, steps):
        rows = candidate_rows_from_scores(frames, component_refs, scores, threshold, temporal_mode)
        summary = summarize_rows(rows, duration)
        candidate = {
            "threshold": threshold,
            "tp_frames": summary["temporal"]["tp_frames"],
            "fn_frames": summary["temporal"]["fn_frames"],
            "fp_frames": summary["temporal"]["fp_frames"],
            "tn_frames": summary["temporal"]["tn_frames"],
        }
        key = (candidate["fn_frames"], candidate["fp_frames"], -candidate["tp_frames"], -threshold)
        if best is None or key < best["selection_key"]:
            best = {**candidate, "selection_key": key}
    assert best is not None
    best.pop("selection_key")
    print(
        f"CALIBRATE candidate={name} done threshold={best['threshold']:.6f} "
        f"tp={best['tp_frames']} fn={best['fn_frames']} fp={best['fp_frames']}",
        flush=True,
    )
    return best


def evaluate_candidate(frames: list[dict], name: str, scorer: CandidateScorer, threshold: float,
                       temporal_mode: str) -> dict:
    started = time.perf_counter_ns()
    component_refs, scores = score_components(frames, name, scorer)
    rows = candidate_rows_from_scores(frames, component_refs, scores, threshold, temporal_mode)
    elapsed_ms = (time.perf_counter_ns() - started) / 1e6
    by_source = {}
    for source_id in sorted({row["source_id"] for row in rows}):
        source_rows = [row for row in rows if row["source_id"] == source_id]
        duration = (
            source_rows[-1]["bag_offset_seconds"] - source_rows[0]["bag_offset_seconds"]
            if len(source_rows) > 1 else 0.0
        )
        by_source[source_id] = summarize_rows(source_rows, duration)
    all_duration = sum(
        source["duration_seconds"] for source in by_source.values()
    )
    total = summarize_rows(rows, all_duration)
    total["sources"] = by_source
    total["candidate"] = name
    total["threshold"] = threshold
    total["evaluation_ms"] = elapsed_ms
    print(
        f"EVAL candidate={name} done raw_fp={total['raw']['fp_frames']} "
        f"temporal_fp={total['temporal']['fp_frames']} "
        f"tp={total['temporal']['tp_frames']} fn={total['temporal']['fn_frames']} "
        f"threshold={threshold:.6f} "
        f"seconds={elapsed_ms / 1000.0:.3f}",
        flush=True,
    )
    return total


def summarize_rows(rows: list[dict], duration_seconds: float) -> dict:
    unknown_rows = [row for row in rows if row["unknown"]]
    unknown_fp_rows = [row for row in unknown_rows if not row["target"]]
    unknown_reasons = sorted({row.get("unknown_reason", "<missing>") for row in unknown_rows})
    raw_fp_keys = [f"{row['source_id']}:{row['frame']}" for row in rows
                   if not row["target"] and (row["unknown"] or row["raw_alarm"])]
    temporal_fp_keys = [f"{row['source_id']}:{row['frame']}" for row in rows
                        if not row["target"] and (row["unknown"] or row["temporal_alarm"])]
    unknown_fp_frame_keys_by_reason = {
        reason: [f"{row['source_id']}:{row['frame']}" for row in unknown_fp_rows
                 if row.get("unknown_reason", "<missing>") == reason]
        for reason in sorted({row.get("unknown_reason", "<missing>") for row in unknown_fp_rows})
    }
    result = {
        "frames": len(rows),
        "unknown": sum(row["unknown"] for row in rows),
        "unknown_reason_counts": dict(Counter(row.get("unknown_reason", "<missing>")
                                              for row in unknown_rows)),
        "unknown_reason_descriptions_ru": {
            reason: UNKNOWN_REASON_DESCRIPTIONS_RU.get(reason, "нет русской расшифровки")
            for reason in unknown_reasons
        },
        "unknown_curve_axis_status_counts": dict(Counter(row.get("curve_axis_status", "<missing>")
                                                         for row in unknown_rows)),
        "unknown_fp_reason_counts": dict(Counter(row.get("unknown_reason", "<missing>")
                                                 for row in unknown_fp_rows)),
        "unknown_fp_frame_keys_by_reason": unknown_fp_frame_keys_by_reason,
        "positive_frames": sum(row["target"] for row in rows),
        "duration_seconds": duration_seconds,
        "raw": {
            "tp_frames": sum(row["target"] and not row["unknown"] and row["target_hit"] for row in rows),
            "fn_frames": sum(row["target"] and (row["unknown"] or not row["target_hit"]) for row in rows),
            "fp_frames": sum(not row["target"] and (row["unknown"] or row["raw_alarm"]) for row in rows),
            "tn_frames": sum(not row["target"] and not row["unknown"] and not row["raw_alarm"] for row in rows),
            "fp_frame_keys": raw_fp_keys,
        },
        "temporal": {
            "tp_frames": sum(row["target"] and not row["unknown"] and row["temporal_target_hit"] for row in rows),
            "fn_frames": sum(row["target"] and (row["unknown"] or not row["temporal_target_hit"]) for row in rows),
            "fp_frames": sum(not row["target"] and (row["unknown"] or row["temporal_alarm"]) for row in rows),
            "tn_frames": sum(not row["target"] and not row["unknown"] and not row["temporal_alarm"] for row in rows),
            "fp_components": sum(row["temporal_false_components"] for row in rows),
            "fp_frame_keys": temporal_fp_keys,
        },
    }
    result["temporal"]["fp_frames_per_minute"] = (
        result["temporal"]["fp_frames"] * 60.0 / duration_seconds
        if duration_seconds > 0 else None
    )
    return result


def add_baseline_fp_overlap(summary: dict) -> None:
    baseline = next((result for result in summary["results"] if result["candidate"] == "legacy_tree_v1"), None)
    if baseline is None:
        return
    baseline_fp = set(baseline["temporal"]["fp_frame_keys"])
    for result in summary["results"]:
        candidate_fp = set(result["temporal"]["fp_frame_keys"])
        common = sorted(candidate_fp & baseline_fp)
        candidate_only = sorted(candidate_fp - baseline_fp)
        baseline_only = sorted(baseline_fp - candidate_fp)
        result["temporal_fp_overlap_vs_legacy_tree_v1"] = {
            "common_fp_frames": len(common),
            "candidate_only_fp_frames": len(candidate_only),
            "baseline_only_fp_frames": len(baseline_only),
            "jaccard": (len(common) / len(candidate_fp | baseline_fp)
                        if candidate_fp or baseline_fp else 1.0),
            "candidate_only_examples": candidate_only[:50],
            "baseline_only_examples": baseline_only[:50],
        }


def add_candidate_baseline_v2_delta(summary: dict) -> None:
    baseline = next((result for result in summary["results"]
                     if result["candidate"] == "candidate_baseline_v2"), None)
    if baseline is None:
        return
    for result in summary["results"]:
        result["delta_vs_candidate_baseline_v2"] = {
            "raw_tp_frames": result["raw"]["tp_frames"] - baseline["raw"]["tp_frames"],
            "raw_fn_frames": result["raw"]["fn_frames"] - baseline["raw"]["fn_frames"],
            "raw_fp_frames": result["raw"]["fp_frames"] - baseline["raw"]["fp_frames"],
            "temporal_tp_frames": result["temporal"]["tp_frames"] - baseline["temporal"]["tp_frames"],
            "temporal_fn_frames": result["temporal"]["fn_frames"] - baseline["temporal"]["fn_frames"],
            "temporal_fp_frames": result["temporal"]["fp_frames"] - baseline["temporal"]["fp_frames"],
        }


def save_trained_models(candidates: dict[str, CandidateScorer], output: Path) -> list[dict]:
    model_dir = output / "trained_models"
    model_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, candidate in candidates.items():
        if candidate.model is None:
            continue
        path = model_dir / f"{name}.pkl"
        with path.open("wb") as handle:
            pickle.dump(candidate.model, handle)
        saved.append({"candidate": name, "path": str(path)})
    manifest = model_dir / "manifest.json"
    manifest.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"TRAIN saved_models count={len(saved)} dir={model_dir}", flush=True)
    return saved


def save_portable_candidate_models(candidates: dict[str, CandidateScorer], thresholds: dict[str, float],
                                   output: Path, summary: dict,
                                   export_candidate_name: str | None,
                                   export_candidate_output: Path | None) -> list[dict]:
    model_dir = output / "trained_models"
    model_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, candidate in candidates.items():
        if candidate.portable_model is None or name == "candidate_baseline_v2":
            continue
        result = next((item for item in summary["results"] if item["candidate"] == name), None)
        model = {
            **candidate.portable_model,
            "threshold": thresholds[name],
            "temporal_rule": summary["temporal_rule"],
            "training": summary["training"],
            "calibration": summary["calibration"],
            "development_evaluation": None if result is None else {
                "evaluation_sources": summary["evaluation_sources"],
                "tp_frames": result["temporal"]["tp_frames"],
                "fn_frames": result["temporal"]["fn_frames"],
                "fp_frames": result["temporal"]["fp_frames"],
                "tn_frames": result["temporal"]["tn_frames"],
                "unknown_fp_frames": result["unknown"],
                "model_temporal_fp_frames": result["temporal"]["fp_frames"] - result["unknown"],
                "threshold": result["threshold"],
            },
        }
        path = model_dir / f"{model['name']}.json"
        path.write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        saved.append({"candidate": name, "path": str(path), "format": model["format"]})
        if export_candidate_name == name and export_candidate_output is not None:
            export_candidate_output.parent.mkdir(parents=True, exist_ok=True)
            export_candidate_output.write_text(
                json.dumps(model, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            saved.append({"candidate": name, "path": str(export_candidate_output),
                          "format": model["format"], "promoted": True})
    if saved:
        manifest = model_dir / "portable_manifest.json"
        manifest.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"TRAIN saved_portable_models count={len(saved)} dir={model_dir}", flush=True)
    return saved


def write_summary_checkpoint(summary: dict, output: Path, label: str) -> None:
    path = output / f"noise_model_candidates.{label}.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CHECKPOINT {path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stream-cli", default="/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    parser.add_argument("--stream-mode", default="2")
    parser.add_argument("--compare-noise-filters", action="store_true",
                        help="Pass through the diagnostic C++ compare flag when the selected image supports it.")
    parser.add_argument("--source", action="append", choices=[item[0] for item in SOURCES])
    parser.add_argument("--train-source", action="append",
                        choices=[item[0] for item in SOURCES])
    parser.add_argument("--training-mode", choices=["current", "hard_negative"], default="current")
    parser.add_argument("--hard-negative-source", action="append", default=[],
                        choices=[item[0] for item in SOURCES],
                        help="Negative sources used to mine legacy_tree_v1 + temporal false-positive components.")
    parser.add_argument("--regular-negative-ratio", type=int, default=20,
                        help="Regular negatives sampled per positive in hard-negative mode.")
    parser.add_argument("--hard-negative-max-duration-seconds", type=float,
                        help="Limit hard-negative mining to the first N seconds of each hard-negative source.")
    parser.add_argument("--synthetic-component-rows", type=Path, action="append", default=[],
                        help="Append synthetic component rows to the component-classifier training set.")
    parser.add_argument("--synthetic-split", default="train",
                        help="Synthetic component_rows split used for training.")
    parser.add_argument("--candidate-baseline-v2", type=Path,
                        default=Path("models/noise_classifier_candidate_baseline_v2.json"),
                        help="Fixed current runtime baseline for evaluation.")
    parser.add_argument("--calibrate-thresholds", action="store_true",
                        help="Pick each candidate threshold on calibration sources before evaluation.")
    parser.add_argument("--calibrate-baseline", action="store_true",
                        help="Also tune the historical legacy_tree_v1 comparator; off by default.")
    parser.add_argument("--calibration-source", action="append", default=[],
                        choices=[item[0] for item in SOURCES])
    parser.add_argument("--calibration-max-duration-seconds", type=float,
                        help="Limit calibration frames to the first N seconds of each calibration source.")
    parser.add_argument("--eval-source-min-offset", action="append", default=[],
                        help="Exclude eval frames before SOURCE:SECONDS, e.g. new_data:600.")
    parser.add_argument("--threshold-steps", type=int, default=51)
    parser.add_argument("--temporal-mode", choices=["causal_runtime", "legacy_adjacent"],
                        default="causal_runtime",
                        help="Temporal confirmation used for offline metrics and calibration.")
    parser.add_argument("--export-candidate-name", choices=[
        "legacy_tree_v1", "decision_tree", "tree_depth3", "tree_depth5_min10",
        "random_forest_lite", "random_forest", "gradient_boosting",
        "lightgbm", "ensemble_v1",
    ])
    parser.add_argument("--export-candidate-output", type=Path)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--last", type=int)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--seed", type=int, default=20260924)
    args = parser.parse_args()
    source_ids = {item[0] for item in SOURCES}
    eval_min_offsets: dict[str, float] = {}
    for value in args.eval_source_min_offset:
        try:
            source_id, seconds = value.split(":", 1)
            if source_id not in source_ids:
                raise ValueError
            eval_min_offsets[source_id] = float(seconds)
        except ValueError as exc:
            raise ValueError("--eval-source-min-offset must be SOURCE:SECONDS") from exc
    if not args.train_source:
        args.train_source = ["doubleT_obstacle"]
    if args.first < 0 or args.last is not None and args.last < args.first:
        raise ValueError("invalid frame range")
    args.output.mkdir(parents=True, exist_ok=True)
    model = json.loads((args.root / "models/noise_classifier_doubleT_obstacle_v1.json").read_text(encoding="utf-8"))
    if model["format"] != "lidar-component-noise-tree-v1":
        raise ValueError("unexpected frozen model format")
    eval_sources = set(args.source) if args.source else None
    hard_negative_sources = set(args.hard_negative_source)
    calibration_sources = set(args.calibration_source)
    load_sources = None if eval_sources is None else eval_sources | set(args.train_source)
    if load_sources is not None:
        load_sources |= hard_negative_sources | calibration_sources
    frames = load_frames(args.root, args.stream_cli, args.stream_mode, args.compare_noise_filters,
                         load_sources,
                         args.first, args.last, args.duration_seconds)
    if args.training_mode == "hard_negative":
        if not hard_negative_sources:
            raise ValueError("--training-mode hard_negative requires at least one --hard-negative-source")
        annotate_legacy_tree_v1_temporal(frames, model["tree"], 0.5, args.temporal_mode)
        rows, training_summary = hard_negative_training_rows(
            frames, set(args.train_source), hard_negative_sources,
            args.regular_negative_ratio, args.seed,
            args.hard_negative_max_duration_seconds,
        )
    else:
        rows, training_summary = training_rows(frames, set(args.train_source))
    synthetic_summaries = []
    for component_rows_path in args.synthetic_component_rows:
        synthetic_rows, synthetic_summary = synthetic_training_rows(component_rows_path, args.synthetic_split)
        rows.extend(synthetic_rows)
        synthetic_summaries.append(synthetic_summary)
    if synthetic_summaries:
        apply_balanced_weights(rows)
        training_summary["synthetic_training"] = synthetic_summaries
        training_summary["combined_rows_by_role"] = dict(Counter(row["training_role"] for row in rows))
        training_summary["combined_class_counts"] = {
            str(key): value for key, value in Counter(row["label"] for row in rows).items()
        }
    candidates, skipped_candidates = train_candidates(rows, model["tree"], args.seed)
    candidates["candidate_baseline_v2"] = load_forest_lite(args.candidate_baseline_v2)
    saved_models = save_trained_models(candidates, args.output)
    eval_frames = [
        frame for frame in frames
        if (eval_sources is None or frame["source_id"] in eval_sources)
        and frame["bag_offset_seconds"] >= eval_min_offsets.get(frame["source_id"], float("-inf"))
    ]
    calibration_first_offsets: dict[str, float] = {}
    for frame in frames:
        if frame["source_id"] in calibration_sources:
            calibration_first_offsets.setdefault(frame["source_id"], frame["bag_offset_seconds"])
    calibration_frames = []
    for frame in frames:
        if frame["source_id"] not in calibration_sources:
            continue
        if args.calibration_max_duration_seconds is not None:
            if (frame["bag_offset_seconds"] - calibration_first_offsets[frame["source_id"]]
                    >= args.calibration_max_duration_seconds):
                continue
        calibration_frames.append(frame)
    thresholds = {name: 0.5 for name in candidates}
    calibration_results = []
    if args.calibrate_thresholds:
        if not calibration_frames:
            raise ValueError("--calibrate-thresholds requires at least one --calibration-source")
        for name, scorer in candidates.items():
            if name == "candidate_baseline_v2":
                threshold = scorer.portable_model.get("threshold", 0.5)
                calibration = {
                    "threshold": threshold,
                    "fixed_baseline": True,
                    "source": str(args.candidate_baseline_v2),
                }
                thresholds[name] = threshold
            elif name == "legacy_tree_v1" and not args.calibrate_baseline:
                calibration_result = evaluate_candidate(calibration_frames, name, scorer, 0.5,
                                                        args.temporal_mode)
                calibration = {
                    "threshold": 0.5,
                    "fixed_baseline": True,
                    "tp_frames": calibration_result["temporal"]["tp_frames"],
                    "fn_frames": calibration_result["temporal"]["fn_frames"],
                    "fp_frames": calibration_result["temporal"]["fp_frames"],
                    "tn_frames": calibration_result["temporal"]["tn_frames"],
                }
            else:
                calibration = calibrate_threshold(calibration_frames, name, scorer, args.threshold_steps,
                                                  args.temporal_mode)
                thresholds[name] = calibration["threshold"]
            calibration["candidate"] = name
            calibration_results.append(calibration)
    thresholds["candidate_baseline_v2"] = candidates["candidate_baseline_v2"].portable_model.get(
        "threshold", thresholds.get("candidate_baseline_v2", 0.5)
    )
    summary = {
        "scope": "OFFLINE_CANDIDATE_SCREENING_MODEL_PLUS_TEMPORAL",
        "temporal_mode": args.temporal_mode,
        "temporal_rule": temporal_rule_description(args.temporal_mode),
        "metric_rule": "Frame metrics count negative UNKNOWN frames as FP; positive UNKNOWN frames count as FN.",
        "fixed_runtime_baseline": {
            "candidate": "candidate_baseline_v2 + temporal",
            "model": str(args.candidate_baseline_v2),
            "threshold": thresholds.get("candidate_baseline_v2"),
        },
        "historical_comparator": {"candidate": "legacy_tree_v1 + temporal", "tp_frames": 52,
                                  "fn_frames": 0, "fp_frames": 463, "tn_frames": 13244},
        "evaluation_sources": sorted(eval_sources) if eval_sources is not None else "all",
        "eval_min_offsets": eval_min_offsets,
        "training": {"sources": args.train_source, "component_count": len(rows),
                     "class_counts": dict(Counter(row["label"] for row in rows)),
                     **training_summary},
        "calibration": {"enabled": args.calibrate_thresholds,
                        "sources": sorted(calibration_sources),
                        "threshold_steps": args.threshold_steps,
                        "max_duration_seconds": args.calibration_max_duration_seconds,
                        "results": calibration_results},
        "skipped_candidates": skipped_candidates,
        "saved_models": saved_models,
        "saved_portable_models": [],
        "results": [],
    }
    write_summary_checkpoint(summary, args.output, "training_done")
    for name, scorer in candidates.items():
        result = evaluate_candidate(eval_frames, name, scorer, thresholds[name], args.temporal_mode)
        summary["results"].append(result)
        add_baseline_fp_overlap(summary)
        add_candidate_baseline_v2_delta(summary)
        write_summary_checkpoint(summary, args.output, f"after_{name}")
    add_baseline_fp_overlap(summary)
    add_candidate_baseline_v2_delta(summary)
    portable_models = save_portable_candidate_models(
        candidates, thresholds, args.output, summary,
        args.export_candidate_name, args.export_candidate_output,
    )
    summary["saved_portable_models"] = portable_models
    summary["ranking_by_temporal_fp"] = sorted(
        [{"candidate": result["candidate"],
          "temporal_fp_frames": result["temporal"]["fp_frames"],
          "temporal_tp_frames": result["temporal"]["tp_frames"],
          "temporal_fn_frames": result["temporal"]["fn_frames"]}
         for result in summary["results"]],
        key=lambda item: (item["temporal_fn_frames"], item["temporal_fp_frames"]),
    )
    path = args.output / "noise_model_candidates.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "ranking": summary["ranking_by_temporal_fp"],
                      "skipped_candidates": skipped_candidates}, ensure_ascii=False))


if __name__ == "__main__":
    main()
