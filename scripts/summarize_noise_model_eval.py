"""Write compact metrics from evaluate_noise_model_candidates.py output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def temporal_rule_description(temporal_mode: str, fallback: str | None) -> str | None:
    if temporal_mode == "causal_runtime":
        return (
            "causal runtime-style confirmation: current alarm and at least one previous "
            "consecutive alarm in the same source; UNKNOWN/source boundary resets state"
        )
    if temporal_mode == "legacy_adjacent":
        return (
            "legacy diagnostic adjacent confirmation: current alarm and at least one "
            "previous or next adjacent alarm in the same source"
        )
    return fallback


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--temporal-mode-override")
    args = parser.parse_args()
    summary = json.loads(args.input.read_text(encoding="utf-8"))
    rows = []
    for result in summary["results"]:
        rows.append({
            "candidate": result["candidate"],
            "threshold": result["threshold"],
            "unknown_fp": result["unknown"],
            "model_temporal_fp": result["temporal"]["fp_frames"] - result["unknown"],
            "fp_total": result["temporal"]["fp_frames"],
            "tp": result["temporal"]["tp_frames"],
            "fn": result["temporal"]["fn_frames"],
            "tn": result["temporal"]["tn_frames"],
            "raw_fp": result["raw"]["fp_frames"],
        })
    temporal_mode = args.temporal_mode_override or summary.get("temporal_mode", "<missing>")
    compact = {
        "format": "noise_model_eval_compact_summary_v1",
        "source": str(args.input),
        "scope": summary.get("scope"),
        "temporal_mode": temporal_mode,
        "temporal_rule": temporal_rule_description(temporal_mode, summary.get("temporal_rule")),
        "training": summary.get("training"),
        "calibration": summary.get("calibration"),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(compact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "temporal_mode": compact["temporal_mode"],
        "rows": len(rows),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
