"""Render front-view presentation clips from saved XYZF LiDAR frames.

The generated overlays are for presentation only. They do not modify detector
runtime behavior and must not be interpreted as a safety decision.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
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
RAIL_HALF_GAUGE_M = 0.76

BACKGROUND = "#061018"
CYAN = "#10d7ff"
YELLOW = "#ffd23f"
GREEN = "#60f0a8"
WHITE = "#edf2f7"
RED = "#ff3b30"


@dataclass(frozen=True)
class Camera:
    eye: np.ndarray
    target: np.ndarray
    fov_deg: float = 50.0

    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        forward = self.target - self.eye
        forward = forward / np.linalg.norm(forward)
        up_hint = np.array([0.0, 0.0, 1.0])
        right = np.cross(up_hint, forward)
        right = right / np.linalg.norm(right)
        up = np.cross(forward, right)
        up = up / np.linalg.norm(up)
        return forward, right, up


def load_xyz(path: Path) -> np.ndarray:
    raw = np.fromfile(path, dtype="<f4")
    if raw.size % 3:
        raise ValueError(f"not an xyzf file: {path}")
    return raw.reshape(-1, 3)


def sample_points(points: np.ndarray, maximum: int) -> np.ndarray:
    if len(points) <= maximum:
        return points
    return points[np.linspace(0, len(points) - 1, maximum, dtype=np.int64)]


def expand_to_duration(records: list[dict], total_frames: int) -> list[dict]:
    if not records:
        raise ValueError("empty frame sequence")
    return [records[round(i * (len(records) - 1) / max(1, total_frames - 1))] for i in range(total_frames)]


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
    return np.column_stack((np.zeros_like(forward), -forward, -1.0 + np.zeros_like(forward)))


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

    distances = [0.0, 3.0, 7.0, 10.0, 14.0, 20.0, 30.0, 45.0, 60.0, 80.0]
    points = [interpolate_or_extrapolate(centers, distance) for distance in distances]
    return np.asarray(points, dtype=float)


def tangent_normal_xy(centerline: np.ndarray, index: int) -> tuple[np.ndarray, np.ndarray]:
    if index <= 0:
        tangent = centerline[1, :2] - centerline[0, :2]
    elif index >= len(centerline) - 1:
        tangent = centerline[-1, :2] - centerline[-2, :2]
    else:
        tangent = centerline[index + 1, :2] - centerline[index - 1, :2]
    norm = np.linalg.norm(tangent)
    if norm < 1e-9:
        tangent = np.array([0.0, -1.0])
    else:
        tangent = tangent / norm
    normal = np.array([tangent[1], -tangent[0]])
    return tangent, normal


def offset_polyline(centerline: np.ndarray, offset: float) -> np.ndarray:
    out = []
    for i, point in enumerate(centerline):
        _, normal = tangent_normal_xy(centerline, i)
        shifted = point.copy()
        shifted[:2] = shifted[:2] + normal * offset
        out.append(shifted)
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


def warning_mask(points: np.ndarray, centerline: np.ndarray) -> np.ndarray:
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


def project(points: np.ndarray, camera: Camera, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    forward, right, up = camera.basis()
    rel = points - camera.eye
    depth = rel @ forward
    x_cam = rel @ right
    y_cam = rel @ up
    tan_half = math.tan(math.radians(camera.fov_deg) / 2.0)
    aspect = width / height
    x_ndc = x_cam / (depth * tan_half * aspect)
    y_ndc = y_cam / (depth * tan_half)
    screen = np.column_stack(((x_ndc + 1.0) * 0.5 * width, (1.0 - y_ndc) * 0.5 * height))
    visible = (
        (depth > 0.6)
        & (x_ndc >= -1.12)
        & (x_ndc <= 1.12)
        & (y_ndc >= -1.12)
        & (y_ndc <= 1.12)
    )
    return screen, visible


def visible_segments(points: np.ndarray, camera: Camera, width: int, height: int) -> np.ndarray:
    segments = []
    for a, b in zip(points[:-1], points[1:]):
        projected, visible = project(np.vstack((a, b)), camera, width, height)
        if visible.all():
            segments.append(projected)
    if not segments:
        return np.empty((0, 2, 2), dtype=float)
    return np.asarray(segments)


def add_segments(axis: plt.Axes, segments: np.ndarray, color: str, linewidth: float, alpha: float = 1.0) -> None:
    if len(segments) == 0:
        return
    axis.add_collection(LineCollection(segments, colors=color, linewidths=linewidth, alpha=alpha))


def envelope_box_segments(center: np.ndarray, normal: np.ndarray, half_width: float) -> list[tuple[np.ndarray, np.ndarray]]:
    z0 = center[2]
    z1 = center[2] + TRAIN_HEIGHT_M
    left_bottom = center.copy()
    right_bottom = center.copy()
    left_top = center.copy()
    right_top = center.copy()
    left_bottom[:2] += normal * half_width
    right_bottom[:2] -= normal * half_width
    left_top[:2] += normal * half_width
    right_top[:2] -= normal * half_width
    left_top[2] = z1
    right_top[2] = z1
    left_bottom[2] = z0
    right_bottom[2] = z0
    return [
        (left_bottom, right_bottom),
        (left_top, right_top),
        (left_bottom, left_top),
        (right_bottom, right_top),
    ]


def draw_envelope_boxes(axis: plt.Axes, centerline: np.ndarray, camera: Camera, width: int, height: int) -> None:
    all_segments = []
    for i, center in enumerate(centerline):
        if -center[1] < 7.0:
            continue
        _, normal = tangent_normal_xy(centerline, i)
        all_segments.extend(envelope_box_segments(center, normal, CORE_HALF_WIDTH_M))
    left = offset_polyline(centerline, CORE_HALF_WIDTH_M)
    right = offset_polyline(centerline, -CORE_HALF_WIDTH_M)
    top_left = left.copy()
    top_right = right.copy()
    top_left[:, 2] += TRAIN_HEIGHT_M
    top_right[:, 2] += TRAIN_HEIGHT_M
    for polyline in (left, right, top_left, top_right):
        all_segments.extend((a, b) for a, b in zip(polyline[:-1], polyline[1:]))
    for a, b in all_segments:
        projected, visible = project(np.vstack((a, b)), camera, width, height)
        if visible.all():
            axis.plot(projected[:, 0], projected[:, 1], color=WHITE, lw=0.95, alpha=0.95)


def draw_projected_polyline(
    axis: plt.Axes,
    points: np.ndarray,
    camera: Camera,
    width: int,
    height: int,
    color: str,
    linewidth: float,
    alpha: float = 1.0,
) -> None:
    add_segments(axis, visible_segments(points, camera, width, height), color, linewidth, alpha)


def draw_distance_labels(axis: plt.Axes, centerline: np.ndarray, camera: Camera, width: int, height: int) -> None:
    label_specs = [
        (3.0, 2.45, "3.0 м", 20),
        (7.0, 2.1, "7.0 м", 11),
        (10.0, 1.7, "10.0 м", 9),
        (14.0, 1.3, "14.0 м", 8),
    ]
    for distance, lateral_offset, text, size in label_specs:
        center = interpolate_or_extrapolate(centerline, distance)
        nearest = int(np.argmin(np.abs(-centerline[:, 1] - distance)))
        _, normal = tangent_normal_xy(centerline, nearest)
        label_point = center.copy()
        label_point[:2] += normal * lateral_offset
        label_point[2] += 0.15
        projected, visible = project(label_point[None, :], camera, width, height)
        if visible[0]:
            axis.text(
                projected[0, 0],
                projected[0, 1],
                text,
                color=YELLOW,
                fontsize=size,
                fontweight="bold",
                ha="center",
                va="center",
                alpha=0.9,
            )


def setup_canvas(axis: plt.Axes, width: int, height: int) -> None:
    axis.clear()
    axis.set_facecolor(BACKGROUND)
    axis.set_xlim(0, width)
    axis.set_ylim(height, 0)
    axis.set_aspect("equal")
    axis.axis("off")


def moving_camera(frame_ordinal: int, total_frames: int) -> Camera:
    phase = 2.0 * math.pi * frame_ordinal / max(1, total_frames - 1)
    eye = np.array([0.12 * math.sin(phase), 2.6, -0.55 + 0.05 * math.sin(phase * 0.7)])
    target = np.array([-0.15, -42.0, -0.82])
    return Camera(eye=eye, target=target)


def obstacle_camera(frame_ordinal: int, total_frames: int, anchor: np.ndarray) -> Camera:
    phase = 2.0 * math.pi * frame_ordinal / max(1, total_frames - 1)
    eye = np.array([0.18 * math.sin(phase), 2.25, -0.55 + 0.04 * math.sin(phase * 0.7)])
    target = anchor + np.array([0.08 * math.sin(phase * 0.5), 0.0, 0.45])
    return Camera(eye=eye, target=target, fov_deg=18.0)


def draw_scene(
    axis: plt.Axes,
    raw: np.ndarray,
    centerline: np.ndarray,
    layer: str,
    camera: Camera,
    width: int,
    height: int,
    sample_max: int,
    obstacle_anchor: np.ndarray | None = None,
    obstacle_distance_m: float | None = None,
) -> dict:
    setup_canvas(axis, width, height)

    centerline = extend_centerline(centerline)
    in_front = raw[(raw[:, 1] < -1.0) & (raw[:, 1] > -92.0) & (raw[:, 2] > -4.8) & (raw[:, 2] < 4.8)]
    shown = sample_points(in_front, sample_max)
    projected, visible = project(shown, camera, width, height)
    if np.any(visible):
        axis.scatter(projected[visible, 0], projected[visible, 1], s=0.25, color=CYAN, alpha=0.72, linewidths=0)

    warning_count = 0
    obstacle_points = 0

    if layer in {"rails", "envelope", "warning", "obstacle"}:
        rail_left = offset_polyline(centerline, RAIL_HALF_GAUGE_M)
        rail_right = offset_polyline(centerline, -RAIL_HALF_GAUGE_M)
        draw_projected_polyline(axis, rail_left, camera, width, height, GREEN, 1.05, 0.9)
        draw_projected_polyline(axis, rail_right, camera, width, height, GREEN, 1.05, 0.9)
        draw_projected_polyline(axis, centerline, camera, width, height, YELLOW, 1.15, 0.96)
        draw_distance_labels(axis, centerline, camera, width, height)

    if layer in {"envelope", "warning", "obstacle"}:
        draw_envelope_boxes(axis, centerline, camera, width, height)

    if layer in {"warning", "obstacle"}:
        mask = warning_mask(in_front, centerline)
        warn = in_front[mask]
        warning_count = int(len(warn))
        warn = sample_points(warn, 32000)
        projected_warn, visible_warn = project(warn, camera, width, height)
        if len(warn) and np.any(visible_warn):
            axis.scatter(
                projected_warn[visible_warn, 0],
                projected_warn[visible_warn, 1],
                s=1.3,
                color=YELLOW,
                alpha=0.9,
                linewidths=0,
            )

    if layer == "obstacle" and obstacle_anchor is not None:
        delta = in_front - obstacle_anchor[None, :]
        obstacle_mask = (
            (np.abs(delta[:, 0]) < 1.25)
            & (np.abs(delta[:, 1]) < 2.0)
            & (delta[:, 2] > -0.65)
            & (delta[:, 2] < 2.6)
        )
        marked = in_front[obstacle_mask]
        obstacle_points = int(len(marked))
        marked = sample_points(marked, 12000)
        projected_marked, visible_marked = project(marked, camera, width, height)
        if len(marked) and np.any(visible_marked):
            axis.scatter(
                projected_marked[visible_marked, 0],
                projected_marked[visible_marked, 1],
                s=18.0,
                color=RED,
                alpha=0.98,
                linewidths=0,
            )
        projected_anchor, visible_anchor = project(obstacle_anchor[None, :], camera, width, height)
        if visible_anchor[0]:
            axis.scatter(projected_anchor[0, 0], projected_anchor[0, 1], s=62, color=RED, edgecolors="white", linewidths=0.8)
        if obstacle_distance_m is not None:
            axis.text(
                10,
                30,
                f"Препятствие на {obstacle_distance_m:0.1f} м",
                color=YELLOW,
                fontsize=18,
                fontweight="bold",
                ha="left",
                va="center",
            )

    return {
        "displayed_points": int(len(shown)),
        "warning_points": warning_count,
        "obstacle_points": obstacle_points,
    }


def load_new_data_records(root: Path, sequence_path: Path) -> list[dict]:
    payload = json.loads(sequence_path.read_text(encoding="utf-8"))
    records = []
    for frame in payload["frames"]:
        pairs = (frame.get("candidate") or {}).get("rail_pairs") or (frame.get("baseline") or {}).get("rail_pairs") or []
        records.append(
            {
                "index": int(frame["index"]),
                "file": root / frame["file"],
                "centerline": centers_from_pairs(pairs),
            }
        )
    return records


def load_doublet_records(root: Path, manifest_path: Path, first: int, last: int) -> list[dict]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = []
    for frame in payload["frames"]:
        index = int(frame["index"])
        if index < first or index > last:
            continue
        baseline = frame.get("stage_3_baseline") or {}
        profiles = baseline.get("path_profiles") or {}
        nodes = (profiles.get("auto_track") or {}).get("nodes") or (baseline.get("path_profile") or {}).get("nodes") or []
        records.append(
            {
                "index": index,
                "file": manifest_path.parent / frame["file"],
                "centerline": centers_from_nodes(nodes),
            }
        )
    return records


def load_obstacle_annotation(path: Path, event_id: str) -> tuple[np.ndarray, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload["point_annotations"]:
        if item["event_id"] == event_id:
            anchor = item["anchor_source_coordinates"]
            return (
                np.array([anchor["x"], anchor["y"], anchor["z"]], dtype=float),
                float(item["approximate_anchor_distance_m"]),
            )
    raise KeyError(event_id)


def render_video(
    records: list[dict],
    output: Path,
    preview: Path,
    layer: str,
    fps: int,
    seconds: int,
    width: int,
    height: int,
    sample_max: int,
    obstacle_anchor: np.ndarray | None = None,
    obstacle_distance_m: float | None = None,
) -> dict:
    total_frames = fps * seconds
    expanded = expand_to_duration(records, total_frames)
    output.parent.mkdir(parents=True, exist_ok=True)
    preview.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    if preview.exists():
        preview.unlink()

    figure, axis = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    figure.patch.set_facecolor(BACKGROUND)
    figure.subplots_adjust(left=0, right=1, bottom=0, top=1)
    writer = FFMpegWriter(fps=fps, codec="libx264", bitrate=6200, extra_args=["-pix_fmt", "yuv420p"])
    summaries = []

    with writer.saving(figure, str(output), dpi=100):
        for ordinal, record in enumerate(expanded):
            if layer == "obstacle" and obstacle_anchor is not None:
                camera = obstacle_camera(ordinal, total_frames, obstacle_anchor)
            else:
                camera = moving_camera(ordinal, total_frames)
            raw = load_xyz(Path(record["file"]))
            anchor = obstacle_anchor
            if layer == "obstacle" and obstacle_anchor is not None and abs(record["index"] - 55) > 18:
                anchor = None
            stats = draw_scene(
                axis,
                raw,
                record["centerline"],
                layer,
                camera,
                width,
                height,
                sample_max,
                anchor,
                obstacle_distance_m,
            )
            writer.grab_frame()
            if ordinal == total_frames // 2:
                figure.savefig(preview, dpi=100, facecolor=BACKGROUND)
            if ordinal in {0, total_frames // 2, total_frames - 1}:
                summaries.append({"ordinal": ordinal, "source_index": record["index"], **stats})

    plt.close(figure)
    return {
        "output": str(output),
        "preview": str(preview),
        "layer": layer,
        "fps": fps,
        "seconds": seconds,
        "frames": total_frames,
        "source_first": expanded[0]["index"],
        "source_last": expanded[-1]["index"],
        "sample_summaries": summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--picts-dir", type=Path, default=Path("docs/presentation/picts"))
    parser.add_argument("--movies-dir", type=Path, default=Path("docs/presentation/movies"))
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--sample-max", type=int, default=115000)
    args = parser.parse_args()

    root = args.root.resolve()
    sequence_path = root / "artefacts/stage_5/rail_axis_video_compare/window_10000.json"
    doublet_manifest = root / "artefacts/stage_2/player_doubleT_obstacle/manifest.json"
    annotations = root / "config/obstacle_annotations_development.json"

    new_data = load_new_data_records(root, sequence_path)
    doublet = load_doublet_records(root, doublet_manifest, first=35, last=84)
    obstacle_anchor, obstacle_distance = load_obstacle_annotation(annotations, "OBS-002")

    jobs = [
        ("01_tunnel.mp4", "generated_01_tunnel.png", new_data, "raw", None, None),
        ("02_rails_axis_distances.mp4", "generated_02_rails_axis_distances.png", new_data, "rails", None, None),
        ("03_train_envelope_80m.mp4", "generated_03_train_envelope_80m.png", new_data, "envelope", None, None),
        ("04_warning_margin_0p5m.mp4", "generated_04_warning_margin_0p5m.png", new_data, "warning", None, None),
        (
            "05_doubleT_obstacle_person.mp4",
            "generated_05_doubleT_obstacle_person.png",
            doublet,
            "obstacle",
            obstacle_anchor,
            obstacle_distance,
        ),
    ]

    manifest = {
        "format": "presentation_perspective_videos_v1",
        "scope": "VISUAL_PRESENTATION_ONLY_NOT_RUNTIME_EVIDENCE",
        "safety_decision_permitted": False,
        "coordinate_basis": "SOURCE_XYZ_UNCHANGED; visual forward is approximately -Y",
        "new_data_sequence": str(sequence_path),
        "doubleT_obstacle_manifest": str(doublet_manifest),
        "videos": [],
    }

    for movie_name, preview_name, records, layer, anchor, distance in jobs:
        print(f"render {movie_name} ({layer}) from {len(records)} source frames")
        result = render_video(
            records,
            args.movies_dir / movie_name,
            args.picts_dir / preview_name,
            layer,
            args.fps,
            args.seconds,
            args.width,
            args.height,
            args.sample_max,
            anchor,
            distance,
        )
        manifest["videos"].append(result)

    manifest_path = args.movies_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
