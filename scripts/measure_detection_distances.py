"""Measure first warning and public detection distances for positive windows.

This is an evidence helper for hackathon reporting. It uses the same direct C++
runtime path as the baseline_v3 evaluator and writes a compact JSON/Markdown
summary for known positive windows only.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import time
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
for extra in (SCRIPT_DIR, REPO_DIR / "src"):
    text = str(extra)
    if text not in sys.path:
        sys.path.insert(0, text)

from archive_bag_frames import ArchiveBagFrames
from cpu_catalog_runtime import DirectDetailedCpuRuntime


@dataclass(frozen=True)
class Window:
    source_id: str
    event_id: str
    description: str
    start: int
    end: int
    window_kind: str


def make_runtime() -> DirectDetailedCpuRuntime:
    return DirectDetailedCpuRuntime(
        rail_selection_method="development_candidate",
        rail_forward_min_m=2.0,
        forward_extension_method="tangent",
        noise_filter_mode="baseline_v3",
    )


def load_windows(labels: dict[str, Any]) -> list[Window]:
    review_items = labels.get("review_object_catalog", [])
    descriptions = {item["object_id"]: item["description_ru"] for item in review_items}
    windows: list[Window] = []
    for source in labels["sources"]:
        source_id = source["source_id"]
        if source_id == "doubleT_obstacle":
            for index, (start, end) in enumerate(source.get("positive_frames_inclusive", []), start=1):
                windows.append(
                    Window(
                        source_id=source_id,
                        event_id=f"positive_{index:02d}",
                        description="real obstacle development interval",
                        start=int(start),
                        end=int(end),
                        window_kind="positive_frames",
                    )
                )
    for item in review_items:
        if item.get("working_role") != "positive":
            continue
        if item.get("review_status") != "user_visible":
            continue
        if "visible_frames_inclusive" not in item:
            continue
        start, end = item["visible_frames_inclusive"]
        windows.append(
            Window(
                source_id="cloud_with_fake_obj",
                event_id=item["object_id"],
                description=item["description_ru"],
                start=int(start),
                end=int(end),
                window_kind="user_visible",
            )
        )
    visible_ids = {window.event_id for window in windows if window.source_id == "cloud_with_fake_obj"}
    for source in labels["sources"]:
        if source["source_id"] != "cloud_with_fake_obj":
            continue
        for event in source.get("positive_events", []):
            object_id = str(event["event_id"]).split("_", 1)[0]
            if object_id in visible_ids:
                continue
            start, end = event["frames_inclusive"]
            windows.append(
                Window(
                    source_id="cloud_with_fake_obj",
                    event_id=event["event_id"],
                    description=descriptions.get(object_id, event["event_id"]),
                    start=int(start),
                    end=int(end),
                    window_kind="scoring_only",
                )
            )
    return windows


def source_by_id(labels: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["source_id"]: source for source in labels["sources"]}


def distance(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) else None


def find_first(rows: list[dict[str, Any]], predicate, distance_key: str) -> dict[str, Any] | None:
    for row in rows:
        result = row["result"]
        if predicate(result):
            return {
                "frame": row["frame_index"],
                "distance_m": distance(result.get(distance_key)),
                "status": result.get("status"),
                "reason": result.get("reason"),
            }
    return None


def find_first_consecutive(
    rows: list[dict[str, Any]],
    predicate,
    distance_key: str,
    required: int,
) -> dict[str, Any] | None:
    run: list[dict[str, Any]] = []
    for row in rows:
        if predicate(row["result"]):
            run.append(row)
            if len(run) >= required:
                current = run[-1]
                result = current["result"]
                first = run[0]
                return {
                    "frame": current["frame_index"],
                    "run_start_frame": first["frame_index"],
                    "distance_m": distance(result.get(distance_key)),
                    "run_start_distance_m": distance(first["result"].get(distance_key)),
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                }
        else:
            run = []
    return None


def analyze_window(
    root: Path,
    source: dict[str, Any],
    window: Window,
    runtime: DirectDetailedCpuRuntime,
) -> dict[str, Any]:
    bag = ArchiveBagFrames(root / source["archive"], source["bag_prefix"], source["source_id"])
    rows: list[dict[str, Any]] = []
    try:
        for frame_index in range(window.start, window.end + 1):
            record, xyz = bag.frame(frame_index)
            result = runtime.analyze(record, xyz)
            rows.append({"frame_index": frame_index, "result": result})
    finally:
        bag.close()

    early = lambda result: result.get("experimental_early_frame_candidate_present") is True
    confirmed = lambda result: result.get("intrusion_candidate_present") is True
    reportable = lambda result: result.get("model_frame_intrusion_candidate_present") is True

    return {
        "source_id": window.source_id,
        "event_id": window.event_id,
        "description": window.description,
        "window_kind": window.window_kind,
        "frames_inclusive": [window.start, window.end],
        "frames_evaluated": len(rows),
        "first_early_candidate": find_first(
            rows, early, "experimental_early_nearest_distance_from_source_origin_m"
        ),
        "first_player_warning_3_consecutive_early": find_first_consecutive(
            rows, early, "experimental_early_nearest_distance_from_source_origin_m", 3
        ),
        "first_frame_reportable_candidate": find_first(
            rows, reportable, "nearest_reportable_intrusion_distance_from_source_origin_m"
        ),
        "first_public_detection": find_first(
            rows, confirmed, "nearest_reportable_intrusion_distance_from_source_origin_m"
        ),
        "first_stable_public_detection_2_consecutive": find_first_consecutive(
            rows, confirmed, "nearest_reportable_intrusion_distance_from_source_origin_m", 2
        ),
    }


def fmt_metric(item: dict[str, Any] | None, *, stable: bool = False) -> str:
    if item is None:
        return "missed"
    value = item.get("distance_m")
    distance_text = "n/a" if value is None else f"{value:.3f} m"
    if stable and item.get("run_start_frame") is not None:
        start_value = item.get("run_start_distance_m")
        start_distance = "n/a" if start_value is None else f"{start_value:.3f} m"
        return f"f{item['frame']} / {distance_text} (run f{item['run_start_frame']} / {start_distance})"
    return f"f{item['frame']} / {distance_text}"


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| source | event | window | frames | player warning 3x | public detection |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['source_id']}` | `{row['event_id']}` {row['description']} | "
            f"{row['window_kind']} | "
            f"{row['frames_inclusive'][0]}..{row['frames_inclusive'][1]} | "
            f"{fmt_metric(row['first_player_warning_3_consecutive_early'])} | "
            f"{fmt_metric(row['first_public_detection'])} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--labels", type=Path, default=Path("config/evaluation_labels.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artefacts/current_model_validation"))
    parser.add_argument("--progress", action="store_true", help="print progress to stderr")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    labels_path = args.labels if args.labels.is_absolute() else root / args.labels
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    sources = source_by_id(labels)
    windows = load_windows(labels)
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    runtime = make_runtime()
    rows: list[dict[str, Any]] = []
    try:
        for index, window in enumerate(windows, start=1):
            if args.progress:
                print(
                    f"window {index}/{len(windows)} {window.source_id} {window.event_id} "
                    f"{window.start}..{window.end}",
                    file=sys.stderr,
                    flush=True,
                )
            rows.append(analyze_window(root, sources[window.source_id], window, runtime))
    finally:
        runtime.close()

    report = {
        "format": "detection_distance_summary_v1",
        "labels": str(labels_path),
        "runtime": {
            "rail_selection_method": "development_candidate",
            "rail_forward_min_m": 2.0,
            "forward_extension_method": "tangent",
            "noise_filter_mode": "baseline_v3",
            "runtime_transport": "direct_cpp",
        },
        "distance_reference": "SOURCE_ORIGIN",
        "distance_units": "m_ASSUMED",
        "positive_windows_only": True,
        "notes": [
            "first_player_warning_3_consecutive_early follows the browser player's orange warning rule",
            "first_public_detection uses intrusion_candidate_present=true",
            "distances are from source LiDAR origin, not train nose",
            "80 m is the envelope search horizon, not measured detection range",
        ],
        "elapsed_wall_seconds": time.monotonic() - started,
        "rows": rows,
    }

    (output_dir / "detection_distance_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "detection_distance_summary.md").write_text(markdown_table(rows), encoding="utf-8")
    print(markdown_table(rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
