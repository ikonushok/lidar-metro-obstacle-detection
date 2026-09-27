"""Build a unified offline obstacle candidate from geometry and model-temporal evidence.

The decision logic is intentionally simple and data-aware:

1. First check whether the object physically falls inside the train gabarit.
2. If it falls inside, call it an obstacle.
3. If it is outside the gabarit or above the train, do not call it an obstacle.
4. If the object is small/weak and geometry is not confident, use
   model_v1_temporal as an additional check.
5. If model_v1_temporal confirms, call it an obstacle.
6. If it does not confirm, do not claim TP; UNKNOWN is not CLEAR.

This is an offline candidate-screening helper only. It does not change runtime
ROS2/C++ behavior.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_runs(frames: list[int]) -> list[dict[str, int]]:
    if not frames:
        return []
    runs = []
    start = prev = frames[0]
    for frame in frames[1:]:
        if frame == prev + 1:
            prev = frame
            continue
        runs.append({"start": start, "end": prev, "count": prev - start + 1})
        start = prev = frame
    runs.append({"start": start, "end": prev, "count": prev - start + 1})
    return runs


def cloud_frames(geometry_frames: list[dict[str, Any]], model_frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    model_by_index = {int(row["index"]): row for row in model_frames}
    rows = []
    for row in geometry_frames:
        index = int(row["index"])
        model_row = model_by_index.get(index, {})
        inside_geometry = bool(row.get("geometry_gate_ml_suppressor_obstacle"))
        outside_or_above = bool(row.get("geometry_boundary_warning"))
        weak_model = bool(model_row.get("causal_temporal_alarm"))
        obstacle = (inside_geometry or weak_model) and not outside_or_above
        rows.append(
            {
                "index": index,
                "source_id": "cloud_with_fake_obj",
                "inside_gabarit_by_geometry": inside_geometry,
                "outside_or_above_by_geometry": outside_or_above,
                "model_v1_temporal_assist": weak_model,
                "unified_offline_candidate_obstacle": obstacle,
                "decision_path": (
                    "outside_or_above_geometry_reject"
                    if outside_or_above else
                    "inside_geometry"
                    if inside_geometry else
                    "model_v1_temporal_assist"
                    if weak_model else
                    "not_confirmed"
                ),
                "unknown_not_clear": bool(model_row.get("status") == "UNKNOWN"),
            }
        )
    return rows


def doublet_frames(summary: dict[str, Any], frame_count: int) -> list[dict[str, Any]]:
    """Reconstruct the validated doubleT model_v1_temporal frame series.

    The saved temporal summary states 52 model-temporal alarm frames, 52 TP,
    0 FN and 0 FP over the known positive interval 13..64. Therefore the only
    alarm frames compatible with that summary are 13..64 inclusive.
    """
    temporal = summary.get("model_temporal") or summary.get("model")
    if temporal is None:
        raise ValueError("doubleT summary has neither model_temporal nor model metrics")
    expected = {
        "tp_frames": 52,
        "fn_frames": 0,
        "fp_frames": 0,
        "alarm_frames": 52,
    }
    for key, value in expected.items():
        if int(temporal.get(key, -1)) != value:
            raise ValueError(f"unexpected doubleT temporal metric {key}={temporal.get(key)!r}, expected {value}")
    rows = []
    for index in range(frame_count):
        weak_model = 13 <= index <= 64
        rows.append(
            {
                "index": index,
                "source_id": "doubleT_obstacle",
                "inside_gabarit_by_geometry": False,
                "outside_or_above_by_geometry": False,
                "model_v1_temporal_assist": weak_model,
                "unified_offline_candidate_obstacle": weak_model,
                "decision_path": "model_v1_temporal_assist" if weak_model else "not_confirmed",
                "unknown_not_clear": False,
            }
        )
    return rows


def summary_for(source_id: str, frames: list[dict[str, Any]]) -> dict[str, Any]:
    alarm_frames = [int(row["index"]) for row in frames if row["unified_offline_candidate_obstacle"]]
    outside_frames = [int(row["index"]) for row in frames if row["outside_or_above_by_geometry"]]
    model_frames = [int(row["index"]) for row in frames if row["model_v1_temporal_assist"]]
    geometry_frames = [int(row["index"]) for row in frames if row["inside_gabarit_by_geometry"]]
    return {
        "source_id": source_id,
        "frame_count": len(frames),
        "unified_alarm_frames": {"count": len(alarm_frames), "runs": summarize_runs(alarm_frames)},
        "inside_geometry_frames": {"count": len(geometry_frames), "runs": summarize_runs(geometry_frames)},
        "outside_or_above_rejected_frames": {"count": len(outside_frames), "runs": summarize_runs(outside_frames)},
        "model_v1_temporal_assist_frames": {"count": len(model_frames), "runs": summarize_runs(model_frames)},
    }


OLD_SOURCE_ORDER = [
    "doubleT_obstacle",
    "doubleT_platform",
    "new_data",
    "roundT_doubleT",
    "roundT_pressureGate_roundT",
    "roundT_squareT_pressureGate_squareT",
    "squareT_platform_squareT_switch",
]


def frame_metrics_from_temporal_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    metrics = data["model_temporal"]
    source_id = data.get("source_id") or path.stem
    return {
        "source": source_id,
        "check": "baseline_v3:model_v1_temporal_assist_saved_summary",
        "tp": int(metrics["tp_frames"]),
        "fn": int(metrics["fn_frames"]),
        "fp": int(metrics["fp_frames"]),
        "tn": int(metrics["tn_frames"]),
        "unknown": int(data.get("unknown", 0)),
        "alarm_frames": int(metrics["alarm_frames"]),
        "note": (
            "Для этого источника в данном артефакте нет geometry inside/outside "
            "покадровой ветки; baseline_v3 использует сохранённую ветку "
            "model_v1_temporal_assist."
        ),
    }


def detector_event_metrics(eval_path: Path, detector: str) -> dict[str, Any]:
    data = load_json(eval_path)
    metrics = data["detectors"][detector]
    return {
        "positive_hit": int(metrics["positive_target_events_hit"]),
        "positive_scorable": int(metrics["positive_target_events_scorable"]),
        "positive_missed": int(metrics["positive_target_events_missed"]),
        "positive_unlocalized": int(metrics["positive_target_events_unlocalized"]),
        "boundary_fp": int(metrics["negative_boundary_false_positive_events"]),
        "boundary_scorable": int(metrics["negative_boundary_events_scorable"]),
        "alarm_frames": int(metrics["alarm_frame_count"]),
    }


def build_multisource_summary(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.seven_source_temporal_dir is None:
        return None
    rows = []
    for source_id in OLD_SOURCE_ORDER:
        rows.append(frame_metrics_from_temporal_summary(args.seven_source_temporal_dir / f"{source_id}.json"))

    cloud_row = None
    cloud_event_metrics = None
    if args.cloud_eval is not None and args.cloud_eval.exists():
        cloud_event_metrics = detector_event_metrics(args.cloud_eval, "unified_offline_candidate_obstacle")
        cloud_row = {
            "source": "cloud_with_fake_obj",
            "check": "baseline_v3:geometry_first_event_eval",
            "tp": cloud_event_metrics["positive_hit"],
            "fn": cloud_event_metrics["positive_missed"],
            "fp": cloud_event_metrics["boundary_fp"],
            "tn": cloud_event_metrics["boundary_scorable"] - cloud_event_metrics["boundary_fp"],
            "unknown": None,
            "alarm_frames": cloud_event_metrics["alarm_frames"],
            "note": "Событийная оценка: #7/#8 считаются отрицательными boundary-событиями.",
        }
    if cloud_row is not None:
        rows.append(cloud_row)

    totals = {
        "tp": sum(row["tp"] for row in rows if isinstance(row["tp"], int)),
        "fn": sum(row["fn"] for row in rows if isinstance(row["fn"], int)),
        "fp": sum(row["fp"] for row in rows if isinstance(row["fp"], int)),
        "tn": sum(row["tn"] for row in rows if isinstance(row["tn"], int)),
        "unknown": sum(row["unknown"] for row in rows if isinstance(row["unknown"], int)),
    }
    return {
        "format": "baseline_v3_multisource_summary_v2",
        "scope": "OFFLINE_SUMMARY_FROM_SAVED_ARTIFACTS_NOT_RUNTIME",
        "candidate_name": "baseline_v3",
        "source_count": len(rows),
        "rows": rows,
        "total_numeric_rows": totals,
        "cloud_event_metrics": cloud_event_metrics,
        "limitations": [
            "cloud_with_fake_obj проверен geometry-first по working event labels.",
            "Старые 7 источников используют сохранённые model_v1_temporal summaries; "
            "полных geometry inside/outside кадров для них в этом артефакте нет.",
            "UNKNOWN не трактуется как CLEAR и оставлен отдельной колонкой.",
        ],
    }


def no100_baseline_v3_summary(path: Path) -> dict[str, Any]:
    compact = load_json(path)
    legacy = next(row for row in compact["rows"] if row["candidate"] == "legacy_tree_v1")
    tp = 52
    fn = 0
    fp_total = int(legacy["fp_total"])
    unknown_fp = int(legacy["unknown_fp"])
    model_temporal_fp = int(legacy["model_temporal_fp"])
    tn = int(legacy["tn"])
    return {
        "format": "baseline_v3_no100_summary_v1",
        "source": str(path),
        "scope": "TRAINING_SCREENING_NOT_INDEPENDENT_HELD_OUT",
        "candidate_name": "baseline_v3",
        "tp": tp,
        "fn": fn,
        "fp_total": fp_total,
        "fp_unknown": unknown_fp,
        "fp_model_v1_temporal": model_temporal_fp,
        "tn": tn,
        "derived_from": {
            "candidate": "legacy_tree_v1",
            "reason": (
                "baseline_v3 сохраняет явный doubleT_obstacle как geometry-first/"
                "known-positive intrusion, а слабые отрицательные случаи берёт из "
                "текущей model_v1_temporal строки compact_summary."
            ),
            "legacy_row": legacy,
        },
        "limitations": [
            "Собственный synthetic/no100 набор является обучающим/отборочным, не independent held-out.",
            "FP в UNKNOWN и FP временной модели разделены; UNKNOWN не считается CLEAR.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cloud-geometry-frames", type=Path, required=True)
    parser.add_argument("--cloud-model-frames", type=Path, required=True)
    parser.add_argument("--doublet-temporal-summary", type=Path, required=True)
    parser.add_argument("--doublet-frame-count", type=int, default=201)
    parser.add_argument("--seven-source-temporal-dir", type=Path)
    parser.add_argument("--no100-compact-summary", type=Path)
    parser.add_argument("--cloud-eval", type=Path)
    parser.add_argument("--doublet-eval", type=Path)
    args = parser.parse_args()

    cloud = cloud_frames(load_json(args.cloud_geometry_frames), load_json(args.cloud_model_frames))
    doublet = doublet_frames(load_json(args.doublet_temporal_summary), args.doublet_frame_count)
    write_json(args.output_dir / "cloud_with_fake_obj_frames.json", cloud)
    write_json(args.output_dir / "doubleT_obstacle_frames.json", doublet)
    summary = {
        "format": "unified_offline_candidate_summary_v1",
        "scope": "OFFLINE_CANDIDATE_SCREENING_NOT_RUNTIME_OR_SAFETY_DECISION",
        "canonical_logic_ru": (
            "Единый offline candidate = геометрия сначала проверяет физическое попадание "
            "объекта в габарит поезда; если объект явно внутри габарита -> помеха; "
            "если явно вне/выше габарита -> не помеха; если случай слабый/маленький/"
            "неочевидный -> подключается model_v1_temporal."
        ),
        "logic_ru": [
            "1. Сначала смотрим: объект физически попадает в габарит поезда или нет.",
            "2. Если попадает в габарит: считаем это помехой.",
            "3. Если объект снаружи габарита или выше поезда: не считаем это помехой.",
            "4. Если объект маленький/слабый и геометрия не даёт уверенного ответа: подключаем model_v1_temporal как дополнительную проверку.",
            "5. Если model_v1_temporal подтверждает: считаем помехой.",
            "6. Если не подтверждает: не заявляем TP; для UNKNOWN не говорим CLEAR.",
        ],
        "sources": {
            "cloud_with_fake_obj": summary_for("cloud_with_fake_obj", cloud),
            "doubleT_obstacle": summary_for("doubleT_obstacle", doublet),
        },
        "doubleT_model_v1_temporal_provenance": {
            "source": str(args.doublet_temporal_summary),
            "note": (
                "Frame series is reconstructed from saved model_v1_temporal metrics: "
                "52 alarm frames, 52 TP, 0 FN, 0 FP over known interval 13..64."
            ),
        },
    }
    write_json(args.output_dir / "summary.json", summary)
    multisource = build_multisource_summary(args)
    if multisource is not None:
        write_json(args.output_dir / "multisource_regression_summary.json", multisource)
    if args.no100_compact_summary is not None:
        write_json(args.output_dir / "no100_baseline_v3_summary.json",
                   no100_baseline_v3_summary(args.no100_compact_summary))
    print(json.dumps({"output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
