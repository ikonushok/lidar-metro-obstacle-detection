"""Render visual-only cloud_with_fake_obj boundary-confirmation sheets.

The renderer reads selected PointCloud2 frames from the ROS bag and overlays
saved raw CORE component extents. It is an offline visual aid only: no detector
decision, runtime policy, envelope, or safety contract is changed here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
import numpy as np  # noqa: E402

import rosbag2_py  # noqa: E402
from rclpy.serialization import deserialize_message  # noqa: E402
from rosidl_runtime_py.utilities import get_message  # noqa: E402
from sensor_msgs_py import point_cloud2  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def component_bounds(row: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    cx, cy, cz = (float(value) for value in row["centroid_xyz"])
    ex, ey, ez = (float(value) for value in row["extent_xyz_m"])
    return (
        cx - ex * 0.5,
        cx + ex * 0.5,
        cy - ey * 0.5,
        cy + ey * 0.5,
        cz - ez * 0.5,
        cz + ez * 0.5,
    )


def candidate_bounds(row: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    first, second = row["bounds_xyz"]
    return (
        float(first[0]),
        float(second[0]),
        float(first[1]),
        float(second[1]),
        float(first[2]),
        float(second[2]),
    )


def read_selected_frames(bag_dir: Path, topic: str, frames: set[int]) -> dict[int, np.ndarray]:
    storage_options = rosbag2_py.StorageOptions(uri=str(bag_dir), storage_id="sqlite3")
    converter_options = rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr")
    reader = rosbag2_py.SequentialReader()
    reader.open(storage_options, converter_options)
    topic_types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    if topic not in topic_types:
        raise KeyError(f"topic {topic!r} missing; available={sorted(topic_types)}")
    msg_type = get_message(topic_types[topic])
    selected: dict[int, np.ndarray] = {}
    frame_index = 0
    while reader.has_next():
        name, data, _timestamp = reader.read_next()
        if name != topic:
            continue
        if frame_index in frames:
            msg = deserialize_message(data, msg_type)
            cloud = point_cloud2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)
            if getattr(cloud, "dtype", None) is not None and cloud.dtype.names:
                points = np.column_stack([cloud["x"], cloud["y"], cloud["z"]]).astype(np.float32, copy=False)
            else:
                points = np.asarray(list(cloud), dtype=np.float32)
            selected[frame_index] = points
        frame_index += 1
        if frames.issubset(selected.keys()):
            break
    missing = sorted(frames - selected.keys())
    if missing:
        raise ValueError(f"missing requested frames: {missing}")
    return selected


def downsample(points: np.ndarray, limit: int) -> np.ndarray:
    if len(points) <= limit:
        return points
    step = max(1, len(points) // limit)
    return points[::step][:limit]


def add_bbox(axis: Any, bounds: tuple[float, float, float, float, float, float], projection: str, color: str, linestyle: str = "-") -> None:
    x0, x1, y0, y1, z0, z1 = bounds
    if projection == "xy":
        rect = Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=color, linewidth=1.6, linestyle=linestyle)
    elif projection == "xz":
        rect = Rectangle((x0, z0), x1 - x0, z1 - z0, fill=False, edgecolor=color, linewidth=1.6, linestyle=linestyle)
    elif projection == "yz":
        rect = Rectangle((y0, z0), y1 - y0, z1 - z0, fill=False, edgecolor=color, linewidth=1.6, linestyle=linestyle)
    else:
        raise ValueError(projection)
    axis.add_patch(rect)


def render_frame_sheet(
    output: Path,
    frame: int,
    points: np.ndarray,
    components: list[dict[str, Any]],
    hanging_candidates: list[dict[str, Any]],
    point_limit: int,
) -> dict[str, Any]:
    shown = downsample(points, point_limit)
    strongest = sorted(components, key=lambda row: int(row["point_count"]), reverse=True)[:5]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.7), constrained_layout=True)
    fig.suptitle(
        f"cloud_with_fake_obj frame {frame} - visual-only raw PointCloud2 with CORE component bboxes",
        fontsize=12,
    )
    views = [
        ("xy", "Top X/Y", 0, 1, "X lateral [m]", "Y forward [m]"),
        ("xz", "Front X/Z", 0, 2, "X lateral [m]", "Z vertical [m]"),
        ("yz", "Side Y/Z", 1, 2, "Y forward [m]", "Z vertical [m]"),
    ]
    colors = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4", "#9467bd"]
    for axis, (projection, title, a, b, xlabel, ylabel) in zip(axes, views):
        axis.scatter(shown[:, a], shown[:, b], s=0.08, c="#2b2b2b", alpha=0.35, rasterized=True)
        for color, row in zip(colors, strongest):
            add_bbox(axis, component_bounds(row), projection, color)
        for row in hanging_candidates[:6]:
            add_bbox(axis, candidate_bounds(row), projection, "#e600e6", "--")
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(True, linewidth=0.3, alpha=0.35)
    axes[0].set_xlim(-3.0, 3.0)
    axes[0].set_ylim(-16.0, -2.0)
    axes[1].set_xlim(-3.0, 3.0)
    axes[1].set_ylim(-2.0, 3.2)
    axes[2].set_xlim(-16.0, -2.0)
    axes[2].set_ylim(-2.0, 3.2)
    text = "\n".join(
        f"{idx+1}: pc={row['point_count']} c=({row['centroid_xyz'][0]:.2f},{row['centroid_xyz'][1]:.2f},{row['centroid_xyz'][2]:.2f}) "
        f"e=({row['extent_xyz_m'][0]:.2f},{row['extent_xyz_m'][1]:.2f},{row['extent_xyz_m'][2]:.2f})"
        for idx, row in enumerate(strongest)
    )
    if hanging_candidates:
        text += "\nHANGING_SCAN: " + "; ".join(
            f"{row['kind']} pc={row['point_count']} c=({row['centroid_xyz'][0]:.2f},{row['centroid_xyz'][1]:.2f},{row['centroid_xyz'][2]:.2f})"
            for row in hanging_candidates[:4]
        )
    fig.text(0.01, 0.01, text, fontsize=8, family="monospace", va="bottom")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return {
        "frame": frame,
        "png": str(output),
        "raw_point_count": int(len(points)),
        "shown_point_count": int(len(shown)),
        "top_components": [
            {
                "point_count": int(row["point_count"]),
                "centroid_xyz": row["centroid_xyz"],
                "extent_xyz_m": row["extent_xyz_m"],
                "min_s_m": row.get("min_s_m"),
                "max_s_m": row.get("max_s_m"),
            }
            for row in strongest
        ],
        "hanging_scan_candidates": hanging_candidates[:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag-dir", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--topic", default="/lidar_points")
    parser.add_argument("--frames", type=int, nargs="+", required=True)
    parser.add_argument("--point-limit", type=int, default=70000)
    parser.add_argument("--hanging-scan", type=Path)
    args = parser.parse_args()

    components = load_json(args.components)
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in components:
        by_frame[int(row["frame"])].append(row)
    requested = set(args.frames)
    hanging_by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if args.hanging_scan:
        scan = load_json(args.hanging_scan)
        for row in scan.get("frames", []):
            hanging_by_frame[int(row["frame"])] = list(row.get("top_candidates", []))
    selected = read_selected_frames(args.bag_dir, args.topic, requested)
    visuals = []
    for frame in sorted(requested):
        visuals.append(
            render_frame_sheet(
                args.output_dir / f"frame_{frame:05d}_raw_component_views.png",
                frame,
                selected[frame],
                by_frame.get(frame, []),
                hanging_by_frame.get(frame, []),
                args.point_limit,
            )
        )
    summary = {
        "format": "cloud_boundary_visual_confirm_v1",
        "scope": "VISUAL_ONLY_NOT_RUNTIME_OR_SAFETY_DECISION",
        "bag_dir": str(args.bag_dir),
        "topic": args.topic,
        "frames": sorted(requested),
        "visuals": visuals,
        "notes": [
            "Axes use source PointCloud2 coordinates; project convention treats X as lateral, Y as forward, Z as vertical for this visual check.",
            "Rectangles are extents of saved raw CORE components, not hand-labelled object boxes.",
            "Dashed magenta rectangles are optional full-cloud hanging-scan candidates when --hanging-scan is provided.",
        ],
    }
    (args.output_dir / "visual_confirm_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(args.output_dir), "frames": sorted(requested)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
