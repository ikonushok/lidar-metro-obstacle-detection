"""Scan full PointCloud2 frames for narrow hanging-object candidates.

This helper is intentionally separate from CORE-component screening: it is used
to localize cloud_with_fake_obj object #10 candidates in the full cloud. It is a
visual/evidence aid only and does not make runtime or safety decisions.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import json
from pathlib import Path
from typing import Any

import numpy as np

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from sensor_msgs_py import point_cloud2


def read_xyz(msg: Any) -> np.ndarray:
    cloud = point_cloud2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)
    if getattr(cloud, "dtype", None) is not None and cloud.dtype.names:
        return np.column_stack([cloud["x"], cloud["y"], cloud["z"]]).astype(np.float32, copy=False)
    return np.asarray(list(cloud), dtype=np.float32)


def cluster_voxels(voxels: np.ndarray, counts: np.ndarray) -> list[dict[str, Any]]:
    if len(voxels) == 0:
        return []
    voxel_to_index = {tuple(value): index for index, value in enumerate(voxels.tolist())}
    seen: set[int] = set()
    clusters = []
    neighbours = [
        (dx, dy, dz)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
        if not (dx == dy == dz == 0)
    ]
    for start in range(len(voxels)):
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        members = []
        while queue:
            index = queue.popleft()
            members.append(index)
            x, y, z = voxels[index]
            for dx, dy, dz in neighbours:
                other = voxel_to_index.get((x + dx, y + dy, z + dz))
                if other is not None and other not in seen:
                    seen.add(other)
                    queue.append(other)
        cluster_voxels_arr = voxels[members]
        cluster_counts = counts[members]
        clusters.append(
            {
                "voxel_indices": members,
                "voxel_min": cluster_voxels_arr.min(axis=0),
                "voxel_max": cluster_voxels_arr.max(axis=0),
                "voxel_count": int(len(members)),
                "point_count": int(cluster_counts.sum()),
            }
        )
    return clusters


def classify(bounds: dict[str, Any], voxel_size: float, crop_origin: np.ndarray) -> str | None:
    vmin = bounds["voxel_min"].astype(np.float32) * voxel_size + crop_origin
    vmax = (bounds["voxel_max"].astype(np.float32) + 1.0) * voxel_size + crop_origin
    extent = vmax - vmin
    centroid = (vmin + vmax) * 0.5
    pc = int(bounds["point_count"])
    if pc >= 25 and extent[0] <= 0.22 and extent[1] <= 0.45 and extent[2] >= 0.55 and centroid[2] >= 0.55:
        return "thin_vertical_hanging_candidate"
    if pc >= 25 and extent[0] <= 0.16 and extent[1] >= 0.90 and extent[2] <= 0.35 and centroid[2] >= 0.90:
        return "thin_upper_longitudinal_candidate"
    if pc >= 18 and extent[0] <= 0.16 and extent[1] <= 0.35 and extent[2] >= 0.35 and centroid[2] >= 1.20:
        return "small_upper_drop_candidate"
    return None


def scan_frame(points: np.ndarray, args: argparse.Namespace) -> list[dict[str, Any]]:
    mask = (
        (np.abs(points[:, 0]) <= args.abs_x_max)
        & (points[:, 1] >= args.y_min)
        & (points[:, 1] <= args.y_max)
        & (points[:, 2] >= args.z_min)
        & (points[:, 2] <= args.z_max)
    )
    cropped = points[mask]
    if len(cropped) == 0:
        return []
    crop_origin = np.array([-args.abs_x_max, args.y_min, args.z_min], dtype=np.float32)
    voxel = np.floor((cropped - crop_origin) / args.voxel_size).astype(np.int32)
    unique, inverse = np.unique(voxel, axis=0, return_inverse=True)
    counts = np.bincount(inverse)
    clusters = cluster_voxels(unique, counts)
    candidates = []
    for cluster in clusters:
        kind = classify(cluster, args.voxel_size, crop_origin)
        if kind is None:
            continue
        vmin = cluster["voxel_min"].astype(np.float32) * args.voxel_size + crop_origin
        vmax = (cluster["voxel_max"].astype(np.float32) + 1.0) * args.voxel_size + crop_origin
        extent = vmax - vmin
        centroid = (vmin + vmax) * 0.5
        candidates.append(
            {
                "kind": kind,
                "point_count": cluster["point_count"],
                "voxel_count": cluster["voxel_count"],
                "centroid_xyz": [float(value) for value in centroid],
                "extent_xyz_m": [float(value) for value in extent],
                "bounds_xyz": [[float(value) for value in vmin], [float(value) for value in vmax]],
            }
        )
    return sorted(
        candidates,
        key=lambda item: (
            item["kind"] != "thin_vertical_hanging_candidate",
            -item["point_count"],
            -item["extent_xyz_m"][2],
        ),
    )


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--topic", default="/lidar_points")
    parser.add_argument("--frame-start", type=int, default=1157)
    parser.add_argument("--frame-end", type=int, default=1509)
    parser.add_argument("--voxel-size", type=float, default=0.08)
    parser.add_argument("--abs-x-max", type=float, default=1.10)
    parser.add_argument("--y-min", type=float, default=-32.0)
    parser.add_argument("--y-max", type=float, default=-2.0)
    parser.add_argument("--z-min", type=float, default=0.20)
    parser.add_argument("--z-max", type=float, default=2.75)
    args = parser.parse_args()

    storage_options = rosbag2_py.StorageOptions(uri=str(args.bag_dir), storage_id="sqlite3")
    converter_options = rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr")
    reader = rosbag2_py.SequentialReader()
    reader.open(storage_options, converter_options)
    topic_types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    if args.topic not in topic_types:
        raise KeyError(f"topic {args.topic!r} missing; available={sorted(topic_types)}")
    msg_type = get_message(topic_types[args.topic])

    frames = []
    frame_index = 0
    while reader.has_next():
        name, data, _timestamp = reader.read_next()
        if name != args.topic:
            continue
        if frame_index > args.frame_end:
            break
        if frame_index >= args.frame_start:
            msg = deserialize_message(data, msg_type)
            candidates = scan_frame(read_xyz(msg), args)
            frames.append(
                {
                    "frame": frame_index,
                    "candidate_count": len(candidates),
                    "top_candidates": candidates[:10],
                    "kind_counts": dict(Counter(item["kind"] for item in candidates)),
                }
            )
        frame_index += 1

    candidate_frames = [row["frame"] for row in frames if row["candidate_count"]]
    top_frames = sorted(
        frames,
        key=lambda row: (
            not any(item["kind"] == "thin_vertical_hanging_candidate" for item in row["top_candidates"]),
            -max((item["point_count"] for item in row["top_candidates"]), default=0),
        ),
    )[:30]
    result = {
        "format": "cloud_hanging_candidate_scan_v1",
        "scope": "FULL_CLOUD_LOCALIZATION_AID_NOT_RUNTIME_OR_SAFETY_DECISION",
        "frame_range": [args.frame_start, args.frame_end],
        "crop": {
            "abs_x_max": args.abs_x_max,
            "y_min": args.y_min,
            "y_max": args.y_max,
            "z_min": args.z_min,
            "z_max": args.z_max,
            "voxel_size": args.voxel_size,
        },
        "candidate_frame_count": len(candidate_frames),
        "candidate_runs": summarize_runs(candidate_frames),
        "top_frames": top_frames,
        "frames": frames,
        "limitations": [
            "This is a geometry prefilter over full cloud points, not GT.",
            "Tunnel ceiling and infrastructure can produce thin candidate-like returns.",
            "Candidates require visual confirmation before changing working labels.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "candidate_frame_count": len(candidate_frames)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
