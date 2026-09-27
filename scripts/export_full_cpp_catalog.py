"""Create a reproducible, source-part C++ CPU catalog for every new_data frame.

The per-frame result is received from curve_envelope_node.  This script does
not calculate rails, envelope membership, or candidates itself.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import time

from cpu_catalog_runtime import CpuCatalogRuntime
from serve_stage_2_catalog import ArchiveFrames, experimental_new_data_overlay


FORMAT = "lidar-cpp-full-catalog-v1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def support_summary(result: dict) -> dict:
    pairs = result.get("rail_pairs_source_xyz", [])
    stations = [float(pair["source_s_m"]) for pair in pairs]
    if not stations:
        return {"available": False, "start_source_s_m": None, "end_source_s_m": None,
                "length_m_assumed": None, "rail_pair_count": 0}
    return {"available": True, "start_source_s_m": min(stations), "end_source_s_m": max(stations),
            "length_m_assumed": max(stations) - min(stations), "rail_pair_count": len(stations)}


def compact_record(index: int, source_part: str, source_part_offset: int,
                   frame: dict, raw_xyzf: bytes, result: dict, runtime_attempts: int) -> dict:
    if str(result.get("header_timestamp_ns")) != str(frame["header_timestamp_ns"]):
        raise ValueError(f"frame {index}: C++ header identity mismatch")
    if result.get("source_frame") != frame["source_frame"]:
        raise ValueError(f"frame {index}: C++ source frame mismatch")
    if result.get("safety_decision_permitted") is not False:
        raise ValueError(f"frame {index}: C++ result is not candidate-only")
    if result.get("rail_selection_method") != "development_candidate":
        raise ValueError(f"frame {index}: C++ method echo mismatch")
    # result is deliberately retained in full: it contains every C++ axis,
    # bound and source index needed by the renderer and later audit.
    return {
        "format": FORMAT,
        "index": index,
        "source_part": source_part,
        "source_part_offset": source_part_offset,
        "identity": {
            "bag_timestamp_ns": frame["bag_timestamp_ns"],
            "bag_offset_seconds": frame["bag_offset_seconds"],
            "header_timestamp_ns": str(frame["header_timestamp_ns"]),
            "source_frame": frame["source_frame"],
            "source_topic": frame["source_topic"],
        },
        "raw_xyzf": {
            "sha256": sha256(raw_xyzf), "bytes": len(raw_xyzf),
            "points": len(raw_xyzf) // 12, "encoding": "FLOAT32_LE_XYZ_IN_SOURCE_ORDER",
        },
        "input_quality": {
            key: frame[key] for key in ("source_points", "finite_points", "zero_xyz_returns", "nonfinite_points")
        },
        "support": support_summary(result),
        "cpp_result": result,
        "matching_cpp_runtime_attempts": runtime_attempts,
        "catalog_recorded_wall_time_ns": time.monotonic_ns(),
    }


def write_json(path: Path, value: dict | list) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def part_name(part_index: int) -> str:
    return f"part_{part_index:03d}.jsonl.gz"


def export(root: Path, output: Path, first_index: int, last_index: int) -> dict:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    overlay = experimental_new_data_overlay(root / "config/geometry_new_data_experiment.yaml")
    archive = ArchiveFrames(root / "dataset/for_hackathon/new_data", overlay)
    if first_index < 0 or last_index < first_index or last_index >= len(archive.lookup):
        raise IndexError("requested frame interval is outside new_data")
    output.mkdir(parents=True)
    (output / "parts").mkdir()
    try:
        source_parts = list(archive.part_counts)
        part_indices = {name: i for i, name in enumerate(source_parts)}
        part_summaries: list[dict] = []
        all_statuses: Counter = Counter()
        all_reasons: Counter = Counter()
        total_core_returns = 0
        total_wall_ms = 0.0
        total_node_ms = 0.0
        node_samples = 0
        ranges_by_part: dict[str, list[int]] = {}
        for index in range(first_index, last_index + 1):
            source_part, _ = archive.lookup[index]
            ranges_by_part.setdefault(source_part, [index, index])[-1] = index
        runtime = CpuCatalogRuntime(rail_selection_method="development_candidate")
        try:
            for source_part, (start, end) in ranges_by_part.items():
                current_records: list[dict] = []
                for index in range(start, end + 1):
                    part_name_from_lookup, source_offset = archive.lookup[index]
                    if part_name_from_lookup != source_part:
                        raise ValueError("source-part interval is not contiguous")
                    frame, raw_xyzf = archive.frame(index)
                    last_timeout = None
                    for runtime_attempts in range(1, 4):
                        try:
                            result = runtime.analyze(frame, raw_xyzf)
                            break
                        except TimeoutError as error:
                            last_timeout = error
                            runtime.close()
                            if runtime_attempts == 3:
                                raise
                            runtime = CpuCatalogRuntime(rail_selection_method="development_candidate")
                    else:
                        raise last_timeout
                    record = compact_record(index, source_part, source_offset, frame, raw_xyzf, result, runtime_attempts)
                    current_records.append(record)
                    all_statuses[result["status"]] += 1
                    all_reasons[result["reason"]] += 1
                    total_core_returns += int(result.get("core_count", 0))
                    total_wall_ms += float(result["wall_processing_ms"])
                    if isinstance(result.get("processing_ms"), (int, float)):
                        total_node_ms += float(result["processing_ms"])
                        node_samples += 1
                with gzip.open(output / "parts" / part_name(part_indices[source_part]), "wt", encoding="utf-8") as target:
                    for record in current_records:
                        target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                supported = sum(item["support"]["available"] for item in current_records)
                unknown = sum(item["cpp_result"]["status"] == "UNKNOWN" for item in current_records)
                core = sum(int(item["cpp_result"].get("core_count", 0)) for item in current_records)
                part_summaries.append({
                    "part_index": part_indices[source_part], "source_part": source_part,
                    "catalog_file": "parts/" + part_name(part_indices[source_part]),
                    "first_index": start, "last_index": end, "frame_count": len(current_records),
                    "support_frame_fraction": supported / len(current_records),
                    "unknown_frame_fraction": unknown / len(current_records),
                    "core_returns_total": core, "core_returns_per_frame": core / len(current_records),
                    "status_counts": dict(Counter(item["cpp_result"]["status"] for item in current_records)),
                    "unknown_reason_counts": dict(Counter(item["cpp_result"]["reason"] for item in current_records
                                                          if item["cpp_result"]["status"] == "UNKNOWN")),
                })
                print(json.dumps({"completed_source_part": source_part, "frames": len(current_records),
                                  "last_index": end}, ensure_ascii=False), flush=True)
        finally:
            runtime.close()
        summary = {
            "format": FORMAT, "scope": "OFFLINE_NEW_DATA_DEVELOPMENT_DIAGNOSTIC_ONLY",
            "safety_decision_permitted": False, "compute_backend": "cpu",
            "rail_selection_method": "development_candidate", "source_archive": "dataset/for_hackathon/new_data",
            "frame_interval_inclusive": [first_index, last_index], "frame_count": last_index - first_index + 1,
            "source_part_count": len(part_summaries), "axis_contract": "hesai_lidar <- hesai_lidar",
            "axes_assumed": {"x": "LATERAL_RIGHT_FACING_FORWARD_ASSUMED",
                             "y": "LONGITUDINAL_FORWARD_IS_NEGATIVE_Y_ASSUMED", "z": "VERTICAL_UP_ASSUMED"},
            "units": "m_ASSUMED", "timing": "header_and_bag_identity_retained_separately; wall uses monotonic clock",
            "status_counts": dict(all_statuses), "reason_counts": dict(all_reasons),
            "core_returns_total": total_core_returns, "wall_processing_ms_total": total_wall_ms,
            "node_processing_ms_total_for_supported_frames": total_node_ms, "node_processing_frame_count": node_samples,
            "parts": part_summaries,
            "limitations": [
                "VIDEO_AND_CATALOG_ARE_DIAGNOSTIC_ONLY_NOT_AXIS_CALIBRATION_OR_OCCLUSION_EVIDENCE",
                "CORE_RETURNS_ARE_OBSERVED_INTRUSION_CANDIDATES_AND_CAN_INCLUDE_INFRASTRUCTURE",
                "UNKNOWN_NEVER_MEANS_CLEAR",
            ],
        }
        write_json(output / "catalog_manifest.json", summary)
        write_json(output / "window_index.json", part_summaries)
        return summary
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    finally:
        archive.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/workspace"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-index", type=int, default=0)
    parser.add_argument("--last-index", type=int)
    args = parser.parse_args()
    if args.last_index is None:
        overlay = experimental_new_data_overlay(args.root / "config/geometry_new_data_experiment.yaml")
        archive = ArchiveFrames(args.root / "dataset/for_hackathon/new_data", overlay)
        try:
            args.last_index = len(archive.lookup) - 1
        finally:
            archive.close()
    print(json.dumps(export(args.root, args.output, args.first_index, args.last_index), ensure_ascii=False))


if __name__ == "__main__":
    main()
