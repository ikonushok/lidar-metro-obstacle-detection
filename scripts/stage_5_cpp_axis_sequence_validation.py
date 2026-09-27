"""Replay fixed Stage-5 sequence windows through the C++ CPU ROS2 node.

This is an offline evidence harness.  It does not implement rail selection,
envelope membership, or viewer classification: each stored result is the JSON
published by ``curve_envelope_node``.  The same source XYZ is replayed once
with each existing C++ rail-selection method.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from math import dist
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import String


WINDOWS = ((1049, 1059), (9995, 10005))
METHODS = ("baseline", "development_candidate")


def load_records(frames_dir: Path) -> list[dict]:
    by_index = {int(item["index"]): item for item in
                map(json.loads, (frames_dir / "frames.jsonl").read_text(encoding="utf-8").splitlines())}
    wanted = [index for first, last in WINDOWS for index in range(first, last + 1)]
    missing = [index for index in wanted if index not in by_index]
    if missing:
        raise ValueError(f"selected sequence frames missing from manifest: {missing}")
    return [by_index[index] for index in wanted]


def cloud_from_xyzf(path: Path, timestamp_ns: str) -> PointCloud2:
    data = path.read_bytes()
    if not data or len(data) % 12:
        raise ValueError(f"{path} is not non-empty float32 XYZ")
    cloud = PointCloud2()
    stamp = int(timestamp_ns)
    cloud.header.frame_id = "hesai_lidar"
    cloud.header.stamp.sec = stamp // 1_000_000_000
    cloud.header.stamp.nanosec = stamp % 1_000_000_000
    cloud.height, cloud.width = 1, len(data) // 12
    cloud.is_bigendian, cloud.is_dense = False, True
    cloud.point_step, cloud.row_step = 12, cloud.width * 12
    cloud.fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    cloud.data = data
    return cloud


def source_path(frames_dir: Path, index: int) -> Path:
    return frames_dir / f"frame_{index:05d}.xyzf"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def support(result: dict) -> dict:
    pairs = result.get("rail_pairs_source_xyz", [])
    if len(pairs) < 2:
        return {
            "status": "NO_GEOMETRIC_SUPPORT",
            "reason": result.get("reason"),
            "observed_pair_stations_s_m": [],
            "envelope_segments": 0,
        }
    stations = [float(pair["source_s_m"]) for pair in pairs]
    centers = [[(left + right) / 2.0 for left, right in zip(pair["left_xyz"], pair["right_xyz"])] for pair in pairs]
    gaps = [right - left for left, right in zip(stations, stations[1:])]
    return {
        "status": "SUPPORTED_BETWEEN_FIRST_AND_LAST_OBSERVED_PAIRS",
        "first_observed_pair_s_m": stations[0],
        "last_observed_pair_s_m": stations[-1],
        "observed_pair_stations_s_m": stations,
        "inter_pair_station_gaps_m": gaps,
        "largest_inter_pair_gap_m": max(gaps),
        "envelope_segments": len(pairs) - 1,
        "axis_polyline_length_m_assumed": sum(dist(a, b) for a, b in zip(centers, centers[1:])),
        "interpretation": (
            "C++ CurveEnvelope sweeps every segment between adjacent selected pairs. "
            "There is no envelope before the first or after the last pair. "
            "A segment spanning an inter-pair gap is geometric interpolation between observed endpoints, "
            "not an observation of all space in that gap."
        ),
    }


def replay_method(records: list[dict], frames_dir: Path, method: str) -> list[dict]:
    process = subprocess.Popen([
        "ros2", "run", "lidar_mosmetro3d_cpp", "curve_envelope_node", "--ros-args",
        "-p", "input_topic:=/axis_validation/cloud",
        "-p", f"output_topic:=/axis_validation/{method}",
        "-p", "source_frame:=hesai_lidar", "-p", "compute_backend:=cpu",
        "-p", f"rail_selection_method:={method}",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    node = rclpy.create_node(f"stage_5_axis_validation_{method}")
    received: list[dict] = []
    publisher = node.create_publisher(PointCloud2, "/axis_validation/cloud", qos_profile_sensor_data)
    node.create_subscription(String, f"/axis_validation/{method}",
                             lambda message: received.append(json.loads(message.data)), 10)
    try:
        results: list[dict] = []
        for record in records:
            source = source_path(frames_dir, int(record["index"]))
            # The source manifest hashes the decoded PointCloud2 source, while
            # this validation replays a derived XYZF export.  They intentionally
            # have different byte representations, so retain both identities
            # rather than treating that fact as corruption.
            actual_hash = sha256(source)
            # The saved visual-window XYZF intentionally retains finite,
            # non-zero returns only; verify that documented export boundary.
            if source.stat().st_size != int(record["input"]["nonzero_finite"]) * 12:
                raise ValueError(f"raw XYZF size does not match documented nonzero export for frame {record['index']}")
            cloud = cloud_from_xyzf(source, str(record["header_timestamp_ns"]))
            deadline = time.monotonic() + 15.0
            matching = None
            while time.monotonic() < deadline:
                publisher.publish(cloud)
                rclpy.spin_once(node, timeout_sec=0.1)
                candidates = [item for item in received if item.get("header_timestamp_ns") == str(record["header_timestamp_ns"])]
                if candidates:
                    matching = candidates[-1]
                    break
            if matching is None:
                stderr = process.stderr.read() if process.poll() is not None else "node still running"
                raise TimeoutError(f"no C++ result for frame {record['index']} ({method}): {stderr}")
            if matching.get("rail_selection_method") != method:
                raise ValueError("C++ method echo does not match request")
            if matching.get("source_frame") != record["input"]["frame"]:
                raise ValueError("C++ source frame does not match manifest")
            if matching.get("safety_decision_permitted") is not False:
                raise ValueError("validation must retain candidate-only safety status")
            if matching.get("curve_axis_status") == "CURVE_AXIS_SUPPORTED":
                counted = sum(int(matching.get(name, 0)) for name in
                              ("core_count", "margin_count", "outside_reference_count", "unknown_count"))
            else:
                counted = int(matching.get("point_count", 0))
            if counted != cloud.width:
                raise ValueError("C++ output point totals do not match exact raw input")
            if sha256(source) != actual_hash:
                raise ValueError("raw XYZF changed while replaying")
            results.append({
                "index": int(record["index"]),
                "header_timestamp_ns": str(record["header_timestamp_ns"]),
                "bag_offset_seconds": float(record["bag_offset_seconds"]),
                "raw_xyzf": source.name,
                "source_record_sha256": record["source_sha256"],
                "raw_xyzf_sha256": actual_hash,
                "replayed_points": int(record["input"]["nonzero_finite"]),
                "excluded_zero_xyz_points": int(record["input"]["zero"]),
                "cpp": matching,
                "support": support(matching),
            })
        return results
    finally:
        node.destroy_node()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)


def transition_rows(results: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for prior, current in zip(results, results[1:]):
        if current["index"] - prior["index"] != 1:
            continue
        before, after = prior["cpp"], current["cpp"]
        rows.append({
            "from_index": prior["index"], "to_index": current["index"],
            "status_change": [before.get("curve_axis_status"), after.get("curve_axis_status")],
            "reason_change": [before.get("reason"), after.get("reason")],
            "rail_pair_count_change": [before.get("rail_pair_count", 0), after.get("rail_pair_count", 0)],
            "interpretation": (
                "Only frame-local selection state is compared. Source coordinates move with the LiDAR; "
                "coordinate displacement between frames is not reported as track/axis error without motion."
            ),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    records = load_records(args.frames_dir)
    args.output.mkdir(parents=True)
    rclpy.init()
    try:
        by_method = {method: replay_method(records, args.frames_dir, method) for method in METHODS}
    finally:
        rclpy.shutdown()
    manifest = {
        "format": "stage_5_cpp_axis_sequence_validation_v1",
        "dataset": "new_data",
        "scope": "TWO_CONNECTED_DEVELOPMENT_WINDOWS; FRAMES_ARE_NOT_INDEPENDENT_RUNS",
        "windows": [{"first_index": first, "last_index": last} for first, last in WINDOWS],
        "compute_backend": "cpu",
        "methods": list(METHODS),
        "same_profile_and_margin": {"core": [-1.4, 1.4, 0.0, 3.7], "margin_each_side_m": 0.5},
        "geometry_basis": "ASSUMED_CURVE_RAIL_AXIS_FROM_SOURCE_XYZ",
        "user_annotation_reference": {
            "path": "config/obstacle_annotations_development.json",
            "available_events": ["OBS-002", "OBS-003"],
            "coverage_of_selected_new_data_windows": "NONE; not used for axis error or event scoring",
        },
        "independent_rail_ground_truth": "NONE_IN_SELECTED_WINDOWS",
        "switch_scene": "NOT_CONFIRMED_FROM_AVAILABLE_METADATA_OR_USER_MARKUP",
        "results": by_method,
        "frame_local_transitions": {method: transition_rows(rows) for method, rows in by_method.items()},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({method: {"frames": len(rows), "supported": sum(item["cpp"].get("curve_axis_status") == "CURVE_AXIS_SUPPORTED" for item in rows)} for method, rows in by_method.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
