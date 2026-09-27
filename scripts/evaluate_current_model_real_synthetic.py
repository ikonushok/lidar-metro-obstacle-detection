"""Evaluate the submitted baseline_v3 pipeline on real and synthetic data.

The script evaluates only the current submitted runtime model:
curve_pipeline_stream_cli 2.0 --use-baseline-v3-filter.

It intentionally does not compare historical/intermediate models.  Outputs are
written to artefacts/ by default, which is ignored by git.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import sys
from typing import Any


REAL_FRAME_SOURCES: dict[str, tuple[str, str]] = {
    "roundT_doubleT": ("for_hackathon/roundT_doubleT", "for_hackathon"),
    "squareT_platform_squareT_switch": ("for_hackathon/squareT_platform_squareT_switch", "for_hackathon"),
    "doubleT_platform": ("for_hackathon/doubleT_platform", "for_hackathon"),
    "roundT_squareT_pressureGate_squareT": ("for_hackathon/roundT_squareT_pressureGate_squareT", "for_hackathon"),
    "doubleT_obstacle": ("for_hackathon/doubleT_obstacle", "for_hackathon"),
    "roundT_pressureGate_roundT": ("for_hackathon/roundT_pressureGate_roundT", "for_hackathon"),
    "new_data": ("new_data", "new_data"),
}

CLOUD_SOURCE = ("cloud_with_fake_obj", "cloud_with_fake_obj")
CLOUD_EVENT_WINDOWS = (
    ("obj01_2x2_center", 204, 216, "positive_target"),
    ("obj02_small_center", 365, 368, "positive_target"),
    ("obj03_small_on_rails", 478, 480, "positive_target"),
    ("obj04_small_edge_inside", 530, 532, "positive_target"),
    ("obj06_2x2_edge_inside", 579, 581, "positive_target"),
    ("obj07_2x2_outside", 630, 633, "negative_boundary"),
    ("obj09_long_low_on_rails", 1138, 1156, "positive_target"),
)

DOUBLET_POSITIVE_FIRST = 13
DOUBLET_POSITIVE_LAST = 64


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_project_paths(root: Path) -> None:
    for child in ("scripts", "src"):
        value = str(root / child)
        if value not in sys.path:
            sys.path.insert(0, value)


def archive_bag_frames_class(root: Path):
    ensure_project_paths(root)
    from archive_bag_frames import ArchiveBagFrames  # noqa: PLC0415

    return ArchiveBagFrames


def default_stream_cli() -> str:
    docker_cli = Path("/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    if docker_cli.exists():
        return str(docker_cli)
    return "curve_pipeline_stream_cli"


def source_archive(root: Path, archive_name: str) -> Path:
    return root / "dataset" / "for_hackathon" / archive_name


def stream_result(process: subprocess.Popen[bytes], raw: bytes, source_id: str, frame: int) -> dict[str, Any]:
    assert process.stdin is not None
    assert process.stdout is not None
    try:
        process.stdin.write(struct.pack("<Q", len(raw) // 12))
        process.stdin.write(raw)
        process.stdin.flush()
    except BrokenPipeError as exc:
        stderr = process.stderr.read().decode(errors="replace")[-2000:] if process.stderr else ""
        raise RuntimeError(f"{source_id} frame {frame}: stream pipe closed: {stderr}") from exc
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read().decode(errors="replace")[-2000:] if process.stderr else ""
        raise RuntimeError(f"{source_id} frame {frame}: stream stopped: {stderr}")
    return json.loads(line)


def close_process(process: subprocess.Popen[bytes]) -> None:
    if process.stdin:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def evaluate_real_frames(
    root: Path,
    stream_cli: str,
    sources: list[str],
    duration_seconds: float | None,
) -> dict[str, Any]:
    ArchiveBagFrames = archive_bag_frames_class(root)
    totals = Counter()
    rows: list[dict[str, Any]] = []

    for source_id in sources:
        prefix, archive_name = REAL_FRAME_SOURCES[source_id]
        source = ArchiveBagFrames(source_archive(root, archive_name), prefix, source_id)
        process = subprocess.Popen(
            [stream_cli, "2.0", "--use-baseline-v3-filter"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        counts = Counter()
        first_offset = None
        try:
            for frame in range(len(source.lookup)):
                record, raw = source.frame(frame)
                if first_offset is None:
                    first_offset = float(record["bag_offset_seconds"])
                if duration_seconds is not None and float(record["bag_offset_seconds"]) - first_offset > duration_seconds:
                    break
                result = stream_result(process, raw, source_id, frame)
                if result.get("noise_filter_mode") != "baseline_v3":
                    raise ValueError(f"{source_id} frame {frame}: current model is not active")
                if result.get("safety_decision_permitted") is not False:
                    raise ValueError(f"{source_id} frame {frame}: safety contract changed")

                target = source_id == "doubleT_obstacle" and DOUBLET_POSITIVE_FIRST <= frame <= DOUBLET_POSITIVE_LAST
                alarm = bool(result.get("intrusion_candidate_present"))
                unknown = result.get("status") == "UNKNOWN"
                counts["frames"] += 1
                counts["unknown"] += int(unknown)
                counts["target_frames"] += int(target)
                if target and alarm:
                    counts["tp"] += 1
                elif target and not alarm:
                    counts["fn"] += 1
                elif not target and alarm:
                    counts["fp_alarm"] += 1
                else:
                    counts["tn"] += 1
                if not target and unknown:
                    counts["negative_unknown"] += 1
                if frame and frame % 1000 == 0:
                    print(f"{source_id}: {frame}/{len(source.lookup)}", flush=True)
        finally:
            source.close()
            close_process(process)

        rows.append({"source_id": source_id, **dict(counts)})
        totals.update(counts)

    fp_or_unknown = int(totals["fp_alarm"] + totals["negative_unknown"])
    return {
        "sources": sources,
        "duration_seconds_per_source": duration_seconds,
        "positive_rule": {
            "source_id": "doubleT_obstacle",
            "frames_inclusive": [DOUBLET_POSITIVE_FIRST, DOUBLET_POSITIVE_LAST],
        },
        "rows": rows,
        "totals": {
            **dict(totals),
            "fp_or_unknown": fp_or_unknown,
            "recall": safe_ratio(int(totals["tp"]), int(totals["tp"] + totals["fn"])),
            "precision_if_unknown_counts_as_fp": safe_ratio(int(totals["tp"]), int(totals["tp"] + fp_or_unknown)),
        },
    }


def evaluate_cloud_events(root: Path, stream_cli: str) -> dict[str, Any]:
    ArchiveBagFrames = archive_bag_frames_class(root)
    prefix, archive_name = CLOUD_SOURCE
    source = ArchiveBagFrames(source_archive(root, archive_name), prefix, "cloud_with_fake_obj")
    process = subprocess.Popen(
        [stream_cli, "2.0", "--use-baseline-v3-filter"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows = []
    try:
        for event_id, first, last, event_class in CLOUD_EVENT_WINDOWS:
            hits = []
            unknowns = []
            for frame in range(first, last + 1):
                _record, raw = source.frame(frame)
                result = stream_result(process, raw, "cloud_with_fake_obj", frame)
                if result.get("noise_filter_mode") != "baseline_v3":
                    raise ValueError(f"cloud_with_fake_obj frame {frame}: current model is not active")
                if bool(result.get("intrusion_candidate_present")):
                    hits.append(frame)
                if result.get("status") == "UNKNOWN":
                    unknowns.append(frame)
            rows.append({
                "event_id": event_id,
                "class": event_class,
                "frames_inclusive": [first, last],
                "hit": bool(hits),
                "hit_frames": hits,
                "unknown_frames": unknowns,
            })
    finally:
        source.close()
        close_process(process)

    positive = [row for row in rows if row["class"] == "positive_target"]
    negative = [row for row in rows if row["class"] == "negative_boundary"]
    return {
        "source": "cloud_with_fake_obj",
        "scope": "working event windows, not full box-level GT",
        "scorable_positive_events": len(positive),
        "positive_events_hit": sum(row["hit"] for row in positive),
        "positive_events_missed": sum(not row["hit"] for row in positive),
        "scorable_negative_boundary_events": len(negative),
        "negative_boundary_false_positive_events": sum(row["hit"] for row in negative),
        "rows": rows,
    }


def build_synthetic_dataset(root: Path, output_dir: Path, stream_cli: str) -> None:
    builder = root / "scripts" / "build_current_model_validation_dataset.py"
    command = [
        sys.executable,
        str(builder),
        "--root", str(root),
        "--output", str(output_dir),
        "--stream-cli", stream_cli,
    ]
    subprocess.run(command, check=True)


def synthetic_summary(root: Path, synthetic_dir: Path, stream_cli: str, rebuild: bool) -> dict[str, Any]:
    summary_path = synthetic_dir / "generation_summary.json"
    if rebuild or not summary_path.exists():
        build_synthetic_dataset(root, synthetic_dir, stream_cli)
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = data["baseline_candidate_baseline_v2_component_metrics"]
    positive = int(metrics.get("positive_components", 0))
    tp = int(metrics.get("model_tp_components", 0))
    fn = int(metrics.get("model_fn_components", 0))
    fp = int(metrics.get("model_fp_components", 0))
    return {
        "dataset_version": data.get("dataset_version"),
        "scope": data.get("scope"),
        "source_windows": data.get("source_windows"),
        "manifest_rows": data.get("manifest_rows"),
        "component_rows": data.get("component_rows"),
        "scenarios": data.get("scenarios"),
        "distances_m": data.get("distances_m"),
        "zones": data.get("zones"),
        "visibility_failure_count": len(data.get("visibility_failures", [])),
        "component_metrics": {
            **metrics,
            "recall": safe_ratio(tp, positive),
            "precision": safe_ratio(tp, tp + fp),
            "fn_rate": safe_ratio(fn, positive),
        },
        "limitations": data.get("limitations", []),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=repo_root(),
                        help="project root containing dataset/for_hackathon")
    parser.add_argument("--stream-cli", default=default_stream_cli())
    parser.add_argument("--output", type=Path,
                        default=Path("artefacts/current_model_validation/evaluation_summary.json"))
    parser.add_argument("--synthetic-dir", type=Path,
                        default=Path("artefacts/current_model_validation/synthetic_no100"))
    parser.add_argument("--rebuild-synthetic", action="store_true",
                        help="create the synthetic validation dataset before evaluating")
    parser.add_argument("--source", action="append", choices=sorted(REAL_FRAME_SOURCES),
                        help="real source to evaluate; repeatable; default is all seven real sources")
    parser.add_argument("--real-duration-seconds", type=float,
                        help="optional per-source duration cap for quick local checks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    synthetic_dir = args.synthetic_dir if args.synthetic_dir.is_absolute() else root / args.synthetic_dir
    sources = args.source or list(REAL_FRAME_SOURCES)

    summary = {
        "format": "current_model_real_synthetic_eval_v1",
        "model": "baseline_v3",
        "runtime_command": [args.stream_cli, "2.0", "--use-baseline-v3-filter"],
        "real_frame_metrics": evaluate_real_frames(root, args.stream_cli, sources, args.real_duration_seconds),
        "cloud_with_fake_obj_event_metrics": evaluate_cloud_events(root, args.stream_cli),
        "synthetic_validation_metrics": synthetic_summary(root, synthetic_dir, args.stream_cli, args.rebuild_synthetic),
        "notes": [
            "Only the submitted current model is evaluated; historical/intermediate models are not compared.",
            "UNKNOWN is reported separately and is not treated as CLEAR.",
            "cloud_with_fake_obj uses working event windows because full box-level GT is not available.",
            "Synthetic metrics are development component-level probes, not independent real-world recall proof.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "real_totals": summary["real_frame_metrics"]["totals"],
        "cloud_events": {
            "hit": summary["cloud_with_fake_obj_event_metrics"]["positive_events_hit"],
            "scorable": summary["cloud_with_fake_obj_event_metrics"]["scorable_positive_events"],
        },
        "synthetic_components": summary["synthetic_validation_metrics"]["component_metrics"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
