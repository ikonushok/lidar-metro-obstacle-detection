"""Render short presentation MP4 clips from saved XYZF LiDAR frames.

The overlays are visual-review only. They reuse existing saved frame exports and
do not change detector/runtime behavior or create a safety decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter
from matplotlib.collections import LineCollection
import numpy as np


CORE_HALF_WIDTH_M = 1.4
WARNING_MARGIN_M = 0.5
ENVELOPE_MAX_FORWARD_M = 80.0
TRAIN_HEIGHT_M = 3.7


def load_xyz(path: Path) -> np.ndarray:
    raw = np.fromfile(path, dtype="<f4")
    if raw.size % 3:
        raise ValueError(f"not an xyzf file: {path}")
    return raw.reshape(-1, 3)


def display_sample(points: np.ndarray, maximum: int) -> np.ndarray:
    if len(points) <= maximum:
        return points
    return points[np.linspace(0, len(points) - 1, maximum, dtype=np.int64)]


def expand_to_duration(records: list[dict], total_frames: int) -> list[dict]:
    if not records:
        raise ValueError("empty frame sequence")
    if len(records) == total_frames:
        return records
    return [records[round(i * (len(records) - 1) / max(1, total_frames - 1))]
            for i in range(total_frames)]


def centers_from_pairs(pairs: list[dict]) -> np.ndarray:
    centers = []
    for pair in pairs:
        left = np.asarray(pair["left_xyz"], dtype=float)
        right = np.asarray(pair["right_xyz"], dtype=float)
        centers.append((left + right) / 2.0)
    if not centers:
        return np.empty((0, 3), dtype=float)
    centers = np.asarray(centers)
    return centers[np.argsort(-centers[:, 1])]


def centers_from_nodes(nodes: Iterable[dict]) -> np.ndarray:
    centers = np.asarray([[node["x_m"], node["y_m"], node["z_m"]] for node in nodes], dtype=float)
    if centers.size == 0:
        return np.empty((0, 3), dtype=float)
    return centers[np.argsort(-centers[:, 1])]


def fallback_centerline() -> np.ndarray:
    forward = np.linspace(0.0, ENVELOPE_MAX_FORWARD_M, 9)
    return np.column_stack((np.zeros_like(forward), -forward, np.zeros_like(forward)))


def extend_centerline(centers: np.ndarray, max_forward: float = ENVELOPE_MAX_FORWARD_M) -> np.ndarray:
    if len(centers) < 2:
        return fallback_centerline()
    centers = centers[np.argsort(-centers[:, 1])]
    forward = -centers[:, 1]
    keep = (forward >= 0.0) & (forward <= max_forward)
    centers = centers[keep]
    forward = forward[keep]
    if len(centers) < 2:
        return fallback_centerline()

    result = []
    if forward[0] > 0.0:
        result.append(interpolate_or_extrapolate(centers, 0.0))
    result.extend(centers)
    if forward[-1] < max_forward:
        result.append(interpolate_or_extrapolate(centers, max_forward))
    return np.asarray(result, dtype=float)


def interpolate_or_extrapolate(centers: np.ndarray, target_forward: float) -> np.ndarray:
    forward = -centers[:, 1]
    if target_forward <= forward[0]:
        a, b = centers[0], centers[1]
        fa, fb = forward[0], forward[1]
    elif target_forward >= forward[-1]:
        a, b = centers[-2], centers[-1]
        fa, fb = forward[-2], forward[-1]
    else:
        right = int(np.searchsorted(forward, target_forward))
        a, b = centers[right - 1], centers[right]
        fa, fb = forward[right - 1], forward[right]
    fraction = 0.0 if abs(fb - fa) < 1e-9 else (target_forward - fa) / (fb - fa)
    point = a + (b - a) * fraction
    point[1] = -target_forward
    return point


def offset_polyline_xy(centerline: np.ndarray, offset: float) -> np.ndarray:
    xy = centerline[:, :2]
    out = []
    for i, point in enumerate(xy):
        if i == 0:
            tangent = xy[1] - xy[0]
        elif i == len(xy) - 1:
            tangent = xy[-1] - xy[-2]
        else:
            tangent = xy[i + 1] - xy[i - 1]
        norm = np.linalg.norm(tangent)
        if norm < 1e-9:
            normal = np.array([1.0, 0.0])
        else:
            normal = np.array([tangent[1], -tangent[0]]) / norm
        out.append(point + normal * offset)
    return np.asarray(out)


def nearest_path_coordinates(points: np.ndarray, centerline: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xy = points[:, :2]
    best_distance = np.full(len(points), np.inf, dtype=float)
    best_forward = np.zeros(len(points), dtype=float)
    best_z = np.zeros(len(points), dtype=float)

    for a, b in zip(centerline[:-1], centerline[1:]):
        segment = b[:2] - a[:2]
        length2 = float(segment @ segment)
        if length2 < 1e-9:
            continue
        t = np.clip(((xy - a[:2]) @ segment) / length2, 0.0, 1.0)
        projection = a[:2] + t[:, None] * segment
        delta = xy - projection
        distance = np.sqrt(np.sum(delta * delta, axis=1))
        better = distance < best_distance
        if not np.any(better):
            continue
        best_distance[better] = distance[better]
        forward_a, forward_b = -a[1], -b[1]
        best_forward[better] = forward_a + (forward_b - forward_a) * t[better]
        best_z[better] = a[2] + (b[2] - a[2]) * t[better]
    return best_distance, best_forward, best_z


def warning_points(points: np.ndarray, centerline: np.ndarray) -> np.ndarray:
    lateral, forward, rail_z = nearest_path_coordinates(points, centerline)
    z_rel = points[:, 2] - rail_z
    return (
        (forward >= 0.0)
        & (forward <= ENVELOPE_MAX_FORWARD_M)
        & (lateral > CORE_HALF_WIDTH_M)
        & (lateral <= CORE_HALF_WIDTH_M + WARNING_MARGIN_M)
        & (z_rel >= 0.0)
        & (z_rel <= TRAIN_HEIGHT_M)
    )


def setup_axis(axis: plt.Axes, title: str) -> None:
    axis.set_facecolor("#061018")
    axis.set_xlim(-6.0, 6.0)
    axis.set_ylim(0.0, ENVELOPE_MAX_FORWARD_M)
    axis.set_xlabel("X source, m")
    axis.set_ylabel("forward approx. -Y, m")
    axis.set_title(title, color="white", fontsize=11)
    axis.grid(color="white", alpha=0.12)
    axis.tick_params(colors="#c9d4dd")
    for spine in axis.spines.values():
        spine.set_color("#8393a0")


def draw_line(axis: plt.Axes, xy: np.ndarray, color: str, linewidth: float, alpha: float = 1.0) -> None:
    if len(xy) < 2:
        return
    axis.plot(xy[:, 0], -xy[:, 1], color=color, lw=linewidth, alpha=alpha)


def draw_envelope(axis: plt.Axes, centerline: np.ndarray, half_width: float, color: str,
                  alpha: float, linewidth: float) -> None:
    left = offset_polyline_xy(centerline, half_width)
    right = offset_polyline_xy(centerline, -half_width)
    polygon = np.vstack([left, right[::-1], left[:1]])
    axis.fill(polygon[:, 0], -polygon[:, 1], color=color, alpha=alpha, linewidth=0)
    segments = []
    for side in (left, right):
        segments.extend([[side[i, 0], -side[i, 1]], [side[i + 1, 0], -side[i + 1, 1]]] for i in range(len(side) - 1))
    if segments:
        collection = LineCollection(np.asarray(segments).reshape(-1, 2, 2), colors=color,
                                    linewidths=linewidth, alpha=min(1.0, alpha + 0.35))
        axis.add_collection(collection)


def draw_frame(axis: plt.Axes, raw: np.ndarray, centerline: np.ndarray, title: str, layer: str,
               sample_max: int) -> dict:
    axis.clear()
    setup_axis(axis, title)
    shown = display_sample(raw, sample_max)
    forward = -shown[:, 1]
    visible = (forward >= 0.0) & (forward <= ENVELOPE_MAX_FORWARD_M)
    shown = shown[visible]
    forward = forward[visible]
    axis.scatter(shown[:, 0], forward, s=0.22, c=shown[:, 2], cmap="viridis",
                 alpha=0.42, linewidths=0)

    warn_count = 0
    if layer in {"rails", "envelope", "warning"}:
        rail_left = offset_polyline_xy(centerline, 0.76)
        rail_right = offset_polyline_xy(centerline, -0.76)
        draw_line(axis, rail_left, "#e7f0ff", 1.0, 0.95)
        draw_line(axis, rail_right, "#e7f0ff", 1.0, 0.95)
        draw_line(axis, centerline[:, :2], "#36c8ff", 1.8, 0.95)

    if layer in {"envelope", "warning"}:
        draw_envelope(axis, centerline, CORE_HALF_WIDTH_M, "#4c7dff", 0.16, 1.2)

    if layer == "warning":
        draw_envelope(axis, centerline, CORE_HALF_WIDTH_M + WARNING_MARGIN_M, "#ffd23f", 0.06, 1.0)
        mask = warning_points(raw, centerline)
        warn = raw[mask]
        warn_count = int(len(warn))
        warn = display_sample(warn, 24000)
        if len(warn):
            axis.scatter(warn[:, 0], -warn[:, 1], s=1.7, color="#ffd23f", alpha=0.9, linewidths=0)

    return {"displayed_points": int(len(shown)), "warning_points": warn_count}


def render_video(records: list[dict], output: Path, title: str, layer: str,
                 fps: int, seconds: int, sample_max: int) -> dict:
    total_frames = fps * seconds
    expanded = expand_to_duration(records, total_frames)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    figure, axis = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    figure.patch.set_facecolor("#061018")
    writer = FFMpegWriter(fps=fps, codec="libx264", bitrate=4200, extra_args=["-pix_fmt", "yuv420p"])
    frame_summaries = []
    with writer.saving(figure, str(output), dpi=100):
        for ordinal, record in enumerate(expanded):
            raw = load_xyz(Path(record["file"]))
            centerline = extend_centerline(record["centerline"])
            stats = draw_frame(axis, raw, centerline, title, layer, sample_max)
            axis.text(0.01, 0.98, f"frame {record['index']}  t={ordinal / fps:0.1f}s",
                      transform=axis.transAxes, va="top", ha="left", color="#e7f0ff", fontsize=9)
            writer.grab_frame()
            if ordinal in {0, len(expanded) // 2, len(expanded) - 1}:
                frame_summaries.append({"ordinal": ordinal, "source_index": record["index"], **stats})
    plt.close(figure)
    return {
        "output": output.name,
        "layer": layer,
        "fps": fps,
        "seconds": seconds,
        "source_frames": sorted({int(record["index"]) for record in records}),
        "sample_frame_summaries": frame_summaries,
    }


def new_data_records(sequence_path: Path, root: Path) -> list[dict]:
    data = json.loads(sequence_path.read_text(encoding="utf-8"))
    records = []
    for frame in data["frames"]:
        pairs = frame["candidate"]["rail_pairs"]
        records.append({
            "index": int(frame["index"]),
            "file": str((root / frame["file"]).resolve()),
            "centerline": centers_from_pairs(pairs),
        })
    return records


def doublet_records(manifest_path: Path, root: Path, start: int, count: int) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    frames = manifest["frames"][start:start + count]
    records = []
    for frame in frames:
        baseline = frame.get("stage_3_baseline", {})
        profile = baseline.get("path_profile") or baseline.get("path_profiles", {}).get("auto_track", {})
        nodes = profile.get("nodes") or []
        records.append({
            "index": int(frame["index"]),
            "file": str((base / frame["file"]).resolve()),
            "centerline": centers_from_nodes(nodes) if nodes else fallback_centerline(),
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artefacts/stage_5/presentation_videos_20260925"))
    parser.add_argument("--new-data-sequence", type=Path,
                        default=Path("artefacts/stage_5/rail_axis_video_compare/window_10000.json"))
    parser.add_argument("--doublet-manifest", type=Path,
                        default=Path("artefacts/stage_2/player_doubleT_obstacle/manifest.json"))
    parser.add_argument("--doublet-start", type=int, default=35)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--sample-max", type=int, default=90000)
    args = parser.parse_args()

    root = Path.cwd()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    new_records = new_data_records(args.new_data_sequence, root)
    doublet = doublet_records(args.doublet_manifest, root, args.doublet_start, args.fps * args.seconds)

    jobs = [
        ("01_train_motion_cloud_only.mp4", "1. Train motion: point cloud only", "raw", new_records),
        ("02_train_motion_rails_axis.mp4", "2. Same window: rails and centerline", "rails", new_records),
        ("03_train_motion_envelope_80m.mp4", "3. Envelope visualized to 80 m", "envelope", new_records),
        ("04_train_motion_warning_margin_0p5m.mp4", "4. Points within +0.5 m warning band", "warning", new_records),
        ("05_doubleT_obstacle_person_crossing.mp4", "5. doubleT_obstacle: person crossing window", "warning", doublet),
    ]

    videos = []
    for filename, title, layer, records in jobs:
        videos.append(render_video(records, output / filename, title, layer,
                                   args.fps, args.seconds, args.sample_max))

    manifest = {
        "format": "presentation_video_pack_v1",
        "safety_decision_permitted": False,
        "scope": "VISUAL_DEMO_ONLY_FROM_SAVED_XYZF_FRAMES",
        "new_data_window": "9995..10005 expanded to 5 seconds at presentation playback rate",
        "doubleT_obstacle_window": f"{args.doublet_start}..{args.doublet_start + args.fps * args.seconds - 1}",
        "geometry_note": "Envelope and +0.5 m band use ASSUMED_HACKATHON source coordinates; no CLEAR/NO_OBSTACLE claim.",
        "videos": videos,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
