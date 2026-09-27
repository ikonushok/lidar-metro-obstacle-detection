"""Summarize the stage-5 real-FP/synthetic feasibility gate.

The script reads already-produced JSON artifacts and writes a compact gate
summary.  It does not train models or change runtime defaults.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--feasibility", type=Path, required=True)
    parser.add_argument("--expected-real-fp", type=int, default=232)
    parser.add_argument("--expected-feasibility-valid", type=int, default=288)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    baseline = read_json(args.baseline)
    legacy = next(result for result in baseline["results"] if result["candidate"] == "legacy_tree_v1")
    feasibility_summary = read_json(args.feasibility / "generation_summary.json")
    manifest = read_jsonl(args.feasibility / "manifest.jsonl")

    by_scenario = {}
    for scenario_id in sorted({row["scenario_id"] for row in manifest}):
        rows = [row for row in manifest if row["scenario_id"] == scenario_id]
        observed = [row for row in rows if int(row["synthetic_returns"]) > 0]
        core_positive = [row for row in rows if int(row["positive_component_count"]) > 0]
        by_scenario[scenario_id] = {
            "placements": len(rows),
            "observed_synthetic_returns": len(observed),
            "visibility_failures": len(rows) - len(observed),
            "valid_core_positive_examples": len(core_positive),
            "deficit_to_24_valid_examples": max(0, 24 - len(core_positive)),
            "synthetic_returns_total": sum(int(row["synthetic_returns"]) for row in rows),
            "positive_components_total": sum(int(row["positive_component_count"]) for row in rows),
            "baseline_status_counts": dict(Counter(row["baseline_status"] for row in rows)),
            "visibility_failure_rows": [
                row["row_id"] for row in rows if int(row["synthetic_returns"]) <= 0
            ],
        }

    user_rule_fp = legacy["temporal"]["fp_frames"] + legacy["unknown"]
    valid_core = sum(item["valid_core_positive_examples"] for item in by_scenario.values())
    summary = {
        "format": "stage5_real_fp_synthetic_v1_gate_summary",
        "baseline_model_v1_temporal_current_causal": {
            "source": "new_data",
            "bag_offset_seconds": "[0,600)",
            "frames": legacy["frames"],
            "unknown_counted_as_fp": legacy["unknown"],
            "component_fp_frames_after_temporal": legacy["temporal"]["fp_frames"],
            "fp_frames_user_rule": user_rule_fp,
            "expected_user_supplied_fp_frames": args.expected_real_fp,
            "expectation_match": user_rule_fp == args.expected_real_fp,
            "trainable_fp_frames_with_core_components": legacy["temporal"]["fp_frames"],
            "trainable_fp_components_after_temporal": legacy["temporal"]["fp_components"],
            "duration_seconds": legacy["duration_seconds"],
            "fp_per_minute_user_rule": (
                user_rule_fp * 60.0 / legacy["duration_seconds"]
                if legacy["duration_seconds"] > 0 else None
            ),
        },
        "feasibility_100m": {
            "source_windows": feasibility_summary["source_windows"],
            "manifest_rows": feasibility_summary["manifest_rows"],
            "expected_rows": args.expected_feasibility_valid,
            "valid_core_positive_examples": valid_core,
            "required_valid_core_positive_examples": args.expected_feasibility_valid,
            "passes_gate": valid_core == args.expected_feasibility_valid,
            "visibility_failures": len(feasibility_summary["visibility_failures"]),
            "source_frame_constraint": (
                "Only doubleT_obstacle has lidar_livox; other real archives are hesai_lidar "
                "and were not used for synthetic insertion without a verified transform."
            ),
            "by_scenario": by_scenario,
        },
        "stop_decision": "STOP_FULL_GENERATION_AND_TRAINING",
        "stop_reason": (
            "100m feasibility did not produce the required valid CORE-positive examples; "
            "full 1152 synthetic train generation is forbidden by the experiment stop rule."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "baseline_fp_user_rule": user_rule_fp,
        "baseline_expectation_match": user_rule_fp == args.expected_real_fp,
        "feasibility_valid_core_positive_examples": valid_core,
        "feasibility_passes_gate": valid_core == args.expected_feasibility_valid,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
