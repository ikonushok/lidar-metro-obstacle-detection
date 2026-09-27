"""Create compact, reproducible comparison tables from C++ sequence JSON."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def value(item: dict, key: str, default=None):
    return item["cpp"].get(key, default)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output exists: {args.output}")
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    baseline = {item["index"]: item for item in data["results"]["baseline"]}
    candidate = {item["index"]: item for item in data["results"]["development_candidate"]}
    args.output.mkdir(parents=True)
    rows: list[dict] = []
    for index in sorted(baseline):
        before, after = baseline[index], candidate[index]
        a, b = before["support"], after["support"]
        rows.append({
            "frame_index": index,
            "window": "1049-1059" if index < 2000 else "9995-10005",
            "baseline_axis": value(before, "curve_axis_status"),
            "candidate_axis": value(after, "curve_axis_status"),
            "baseline_reason": value(before, "reason"),
            "candidate_reason": value(after, "reason"),
            "baseline_pair_count": value(before, "rail_pair_count", 0),
            "candidate_pair_count": value(after, "rail_pair_count", 0),
            "baseline_support_s_m": None if "first_observed_pair_s_m" not in a else f"{a['first_observed_pair_s_m']:.1f}..{a['last_observed_pair_s_m']:.1f}",
            "candidate_support_s_m": None if "first_observed_pair_s_m" not in b else f"{b['first_observed_pair_s_m']:.1f}..{b['last_observed_pair_s_m']:.1f}",
            "baseline_axis_length_m_assumed": a.get("axis_polyline_length_m_assumed"),
            "candidate_axis_length_m_assumed": b.get("axis_polyline_length_m_assumed"),
            "baseline_max_inter_pair_gap_m": a.get("largest_inter_pair_gap_m"),
            "candidate_max_inter_pair_gap_m": b.get("largest_inter_pair_gap_m"),
            "baseline_core_returns": value(before, "core_count", 0),
            "candidate_core_returns": value(after, "core_count", 0),
            "baseline_unknown_returns": value(before, "unknown_count", value(before, "point_count", 0)),
            "candidate_unknown_returns": value(after, "unknown_count", value(after, "point_count", 0)),
            "axis_error_metric": "NOT_AVAILABLE_NO_INDEPENDENT_RAIL_MARKS",
            "event_metric": "NOT_AVAILABLE_NO_EVENT_MARKS_IN_NEW_DATA_WINDOWS",
        })
    fields = list(rows[0])
    with (args.output / "per_frame_comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    def supported(method: str, window: str | None = None) -> int:
        chosen = [item for item in data["results"][method] if window is None or (item["index"] < 2000) == (window == "1049-1059")]
        return sum(value(item, "curve_axis_status") == "CURVE_AXIS_SUPPORTED" for item in chosen)
    changed = [row["frame_index"] for row in rows if row["baseline_axis"] != row["candidate_axis"]]
    summary = {
        "format": "stage_5_cpp_axis_sequence_summary_v1",
        "unit_of_analysis": "connected frame windows; frames are not independent runs",
        "frames": len(rows),
        "supported_frames": {
            "baseline": supported("baseline"), "development_candidate": supported("development_candidate"),
            "window_1049_1059": {"baseline": supported("baseline", "1049-1059"), "development_candidate": supported("development_candidate", "1049-1059")},
            "window_9995_10005": {"baseline": supported("baseline", "9995-10005"), "development_candidate": supported("development_candidate", "9995-10005")},
        },
        "candidate_support_added_where_baseline_unknown": changed,
        "baseline_unknown_reasons": sorted({row["baseline_reason"] for row in rows if row["baseline_axis"] != "CURVE_AXIS_SUPPORTED"}),
        "candidate_ambiguity": {
            "reported_ambiguous_statuses": sum("AMBIGUOUS" in row["candidate_reason"] for row in rows),
            "interpretation": "Zero reported statuses is not proof that no competing physical route exists: the C++ output exposes only its selected path/reason, not a ranked alternative set.",
        },
        "axis_error": "NOT_MEASURED: no independent rail-head source-return marks in selected windows; user marks at frame 168 are another scene and are not transferred.",
        "events": "NOT_SCORED: existing OBS-002/OBS-003 user annotations belong to doubleT_obstacle, not selected new_data windows.",
        "support_interpretation": "Supported ranges are C++ envelope geometry between selected pair endpoints. They do not prove absence of occlusion, free space, or a correct route choice.",
        "raw_input_boundary": "Each replayed XYZF contains finite non-zero returns only; excluded zero XYZ counts are recorded per frame in manifest.",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
