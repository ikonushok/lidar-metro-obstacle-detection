"""Render compact, source-part diagnostic previews from a saved C++ catalog.

Raw XYZ is re-read from the original archive and SHA-256 checked against the
catalog before display.  Axis, support, bounds, CORE and MARGIN labels all
come from the matching saved C++ JSON; this renderer performs no membership or
rail detection.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter
import numpy as np

from serve_stage_2_catalog import ArchiveFrames, experimental_new_data_overlay


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_records(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def selected_records(records: list[dict], maximum: int) -> list[dict]:
    if maximum < 1:
        raise ValueError("preview frame count must be positive")
    positions = np.unique(np.linspace(0, len(records) - 1, min(maximum, len(records)), dtype=int))
    return [records[int(position)] for position in positions]


def verify_and_load(archive: ArchiveFrames, record: dict) -> np.ndarray:
    frame, raw = archive.frame(int(record["index"]))
    identity = record["identity"]
    if (str(frame["header_timestamp_ns"]) != identity["header_timestamp_ns"] or
            frame["source_frame"] != identity["source_frame"] or
            frame["source_topic"] != identity["source_topic"]):
        raise ValueError(f"frame {record['index']}: archive identity no longer matches catalog")
    if sha256(raw) != record["raw_xyzf"]["sha256"]:
        raise ValueError(f"frame {record['index']}: raw XYZ SHA-256 mismatch")
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 3)


def draw_envelope_proxy(axis: plt.Axes, result: dict) -> None:
    """Draw only the C++ axis/bounds-derived top-down display proxy.

    This is not a second membership computation: C++ source indices are the
    only labels.  The polygon gives reviewers the C++ core-bound context.
    """
    polyline = np.asarray(result.get("curve_axis_polyline_source_xyz", []), dtype=float)
    bounds = result.get("core_bounds_source_axis")
    if len(polyline) < 2 or not bounds:
        return
    center = polyline[:, :2]
    tangent = np.gradient(center, axis=0)
    lengths = np.linalg.norm(tangent, axis=1)
    valid = lengths > 1e-9
    tangent[valid] /= lengths[valid, None]
    tangent[~valid] = [0.0, -1.0]
    normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    left = center + normal * float(bounds[0])
    right = center + normal * float(bounds[1])
    axis.plot(center[:, 0], -center[:, 1], color="#00b4d8", linewidth=1.5, label="C++ axis")
    axis.plot(left[:, 0], -left[:, 1], color="#90e0ef", linewidth=0.8, linestyle="--")
    axis.plot(right[:, 0], -right[:, 1], color="#90e0ef", linewidth=0.8, linestyle="--")


def draw_frame(axis: plt.Axes, xyz: np.ndarray, record: dict, title: bool = True) -> None:
    result = record["cpp_result"]
    sample = xyz[::max(1, len(xyz) // 7000)]
    axis.scatter(sample[:, 0], -sample[:, 1], s=.25, c="#64748b", alpha=.3, linewidths=0)
    for key, color, size, label in (("margin_source_indices", "#f59e0b", 1.8, "C++ MARGIN"),
                                    ("core_source_indices", "#ef4444", 3.2, "C++ CORE candidate")):
        indices = np.asarray(result.get(key, []), dtype=int)
        if len(indices):
            points = xyz[indices]
            axis.scatter(points[:, 0], -points[:, 1], s=size, c=color, alpha=.82, linewidths=0, label=label)
    draw_envelope_proxy(axis, result)
    support = record["support"]
    if support["available"]:
        text = (f"support s={support['start_source_s_m']:.1f}…{support['end_source_s_m']:.1f} m* | "
                f"CORE={result.get('core_count', 0)}")
    else:
        text = f"NO SUPPORT | {result['reason']}"
    if title:
        axis.set_title(f"#{record['index']}  {result['status']}\n{text}", fontsize=8)
    axis.set(xlim=(-5, 5), ylim=(0, 80), xlabel="X source units", ylabel="forward approx. −Y")
    axis.grid(alpha=.16)
    axis.set_facecolor("#08111f")
    axis.tick_params(colors="#cbd5e1", labelsize=7)
    for spine in axis.spines.values():
        spine.set_color("#64748b")


def render_part(archive: ArchiveFrames, part: dict, catalog_dir: Path, output: Path,
                preview_frames: int, fps: float) -> dict:
    records = read_records(catalog_dir / part["catalog_file"])
    if len(records) != part["frame_count"]:
        raise ValueError(f"{part['source_part']}: catalog frame count mismatch")
    chosen = selected_records(records, preview_frames)
    video_path = output / "videos" / f"part_{part['part_index']:03d}.mp4"
    sheet_path = output / "contact_sheets" / f"part_{part['part_index']:03d}.png"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    figure.patch.set_facecolor("#08111f")
    writer = FFMpegWriter(fps=fps, codec="libx264", bitrate=2200, extra_args=["-pix_fmt", "yuv420p"])
    with writer.saving(figure, str(video_path), dpi=100):
        for record in chosen:
            axis.clear()
            draw_frame(axis, verify_and_load(archive, record), record)
            axis.text(.01, .01, "Diagnostic only: ASSUMED geometry; CORE = C++ candidate, not object class; UNKNOWN ≠ CLEAR",
                      transform=axis.transAxes, color="#fda4af", fontsize=8, va="bottom")
            writer.grab_frame()
    plt.close(figure)

    columns = 4
    rows = int(np.ceil(len(chosen) / columns))
    figure, axes = plt.subplots(rows, columns, figsize=(columns * 4.0, rows * 3.2), dpi=140, squeeze=False)
    figure.patch.set_facecolor("#08111f")
    for axis, record in zip(axes.flat, chosen):
        draw_frame(axis, verify_and_load(archive, record), record)
    for axis in axes.flat[len(chosen):]:
        axis.axis("off")
    figure.suptitle(f"new_data source part {part['part_index']:03d} | frames {part['first_index']}–{part['last_index']} | "
                     "C++ development_candidate diagnostic samples", color="white", fontsize=11)
    figure.tight_layout(rect=(0, 0, 1, .95))
    figure.savefig(sheet_path)
    plt.close(figure)
    return {"part_index": part["part_index"], "source_part": part["source_part"],
            "frame_interval_inclusive": [part["first_index"], part["last_index"]],
            "sampled_catalog_indices": [record["index"] for record in chosen],
            "video": str(video_path.relative_to(catalog_dir)), "contact_sheet": str(sheet_path.relative_to(catalog_dir)),
            "preview_sampling": "EQUALLY_SPACED_WITHIN_SOURCE_PART", "fps": fps}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/workspace"))
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--preview-frames-per-part", type=int, default=12)
    parser.add_argument("--fps", type=float, default=3.0)
    args = parser.parse_args()
    if args.fps <= 0:
        raise ValueError("fps must be positive")
    manifest = json.loads((args.catalog / "catalog_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("rail_selection_method") != "development_candidate" or manifest.get("compute_backend") != "cpu":
        raise ValueError("catalog is not the required C++ CPU development_candidate output")
    output = args.catalog / "previews"
    if output.exists():
        raise FileExistsError(f"preview output already exists: {output}")
    overlay = experimental_new_data_overlay(args.root / "config/geometry_new_data_experiment.yaml")
    archive = ArchiveFrames(args.root / "dataset/for_hackathon/new_data", overlay)
    try:
        rendered = [render_part(archive, part, args.catalog, output, args.preview_frames_per_part, args.fps)
                    for part in manifest["parts"]]
    finally:
        archive.close()
    with (output / "index.csv").open("w", newline="", encoding="utf-8") as target:
        fields = ["part_index", "source_part", "first_index", "last_index", "frame_count", "support_frame_fraction",
                  "unknown_frame_fraction", "core_returns_total", "core_returns_per_frame", "video", "contact_sheet"]
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        by_part = {item["part_index"]: item for item in rendered}
        for part in manifest["parts"]:
            visual = by_part[part["part_index"]]
            writer.writerow({**part, "video": visual["video"], "contact_sheet": visual["contact_sheet"]})
    output_manifest = {"format": "lidar-cpp-catalog-preview-v1", "catalog": "../catalog_manifest.json",
                       "source_part_chapters": rendered, "index_table": "index.csv",
                       "interpretation": "DIAGNOSTIC_ONLY; matching C++ JSON labels; no calibration, occlusion or detection-quality claim"}
    (output / "preview_manifest.json").write_text(json.dumps(output_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"parts": len(rendered), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
