"""Render and summarize roundT_pressureGate_roundT baseline_v3 FP frames.

This is an offline evidence helper. It reads saved component summaries from the
geometry audit and creates visual-only component bounding-box sheets. It does
not change runtime behavior or detector thresholds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def bounds(row: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
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


def component_brief(row: dict[str, Any]) -> dict[str, Any]:
    extent = [float(value) for value in row["extent_xyz_m"]]
    span_s = None
    if row.get("min_s_m") is not None and row.get("max_s_m") is not None:
        span_s = float(row["max_s_m"]) - float(row["min_s_m"])
    return {
        "frame": int(row["frame"]),
        "zone": row.get("zone"),
        "point_count": int(row["point_count"]),
        "min_s_m": row.get("min_s_m"),
        "max_s_m": row.get("max_s_m"),
        "s_span_m": span_s,
        "nearest_distance_m": row.get("nearest_distance_m"),
        "centroid_xyz": row.get("centroid_xyz"),
        "extent_xyz_m": row.get("extent_xyz_m"),
        "extent_y_to_x_ratio": (
            None if extent[0] <= 1e-9 else extent[1] / extent[0]
        ),
        "extent_y_to_z_ratio": (
            None if extent[2] <= 1e-9 else extent[1] / extent[2]
        ),
    }


def add_rect(axis: Any, row: dict[str, Any], projection: str, color: str, linewidth: float,
             linestyle: str = "-") -> None:
    x0, x1, y0, y1, z0, z1 = bounds(row)
    if projection == "xy":
        rect = Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=color,
                         linewidth=linewidth, linestyle=linestyle)
    elif projection == "xz":
        rect = Rectangle((x0, z0), x1 - x0, z1 - z0, fill=False, edgecolor=color,
                         linewidth=linewidth, linestyle=linestyle)
    elif projection == "yz":
        rect = Rectangle((y0, z0), y1 - y0, z1 - z0, fill=False, edgecolor=color,
                         linewidth=linewidth, linestyle=linestyle)
    else:
        raise ValueError(projection)
    axis.add_patch(rect)


def frame_components(components: list[dict[str, Any]], frame: int, minimum_points: int) -> list[dict[str, Any]]:
    rows = [
        row for row in components
        if int(row["frame"]) == frame
        and row.get("zone", "core") == "core"
        and int(row.get("point_count", 0)) >= minimum_points
    ]
    return sorted(rows, key=lambda item: int(item["point_count"]), reverse=True)


def render_sheet(
    output: Path,
    components: list[dict[str, Any]],
    frames: list[int],
    fp_frames: set[int],
    minimum_points: int,
) -> list[dict[str, Any]]:
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.3), constrained_layout=True)
    fig.suptitle(
        "roundT_pressureGate_roundT FP inspection: CORE component extents, visual-only",
        fontsize=12,
    )
    views = [
        ("xy", "Top X/Y", "X lateral [m]", "Y source [m]", (-2.5, 2.5), (-20.0, -1.0)),
        ("xz", "Front X/Z", "X lateral [m]", "Z source [m]", (-2.5, 2.5), (-1.4, 0.1)),
        ("yz", "Side Y/Z", "Y source [m]", "Z source [m]", (-20.0, -1.0), (-1.4, 0.1)),
    ]
    plotted = []
    for axis, (projection, title, xlabel, ylabel, xlim, ylim) in zip(axes, views):
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.set_xlim(*xlim)
        axis.set_ylim(*ylim)
        axis.grid(True, alpha=0.25, linewidth=0.4)
        for frame in frames:
            rows = frame_components(components, frame, minimum_points)
            for index, row in enumerate(rows[:5]):
                is_fp = frame in fp_frames and index == 0 and int(row["point_count"]) >= 1000
                color = "#d62728" if is_fp else "#7f7f7f"
                linewidth = 2.6 if is_fp else 1.0
                linestyle = "-" if is_fp else "--"
                add_rect(axis, row, projection, color, linewidth, linestyle)
                if projection == "xy":
                    cx, cy, _cz = row["centroid_xyz"]
                    axis.text(float(cx), float(cy), str(frame), color=color, fontsize=8)
    for frame in frames:
        rows = frame_components(components, frame, minimum_points)
        plotted.append({
            "frame": frame,
            "is_baseline_v3_fp": frame in fp_frames,
            "top_components": [component_brief(row) for row in rows[:5]],
        })
    fig.text(
        0.01,
        0.01,
        "red solid = baseline_v3 FP strong geometry component; gray dashed = neighboring high-support CORE components",
        fontsize=9,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170)
    plt.close(fig)
    return plotted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--union-frames", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-id", default="roundT_pressureGate_roundT")
    parser.add_argument("--frames", type=int, nargs="+", default=[108, 109, 110, 111, 112, 113, 114])
    parser.add_argument("--minimum-points", type=int, default=250)
    args = parser.parse_args()

    components = load_json(args.components)
    union_rows = load_json(args.union_frames)
    fp_frames = {
        int(row["frame"])
        for row in union_rows
        if row.get("source") == args.source_id and row.get("baseline_v3_obstacle")
    }
    selected_fp = sorted(set(args.frames) & fp_frames)
    plotted = render_sheet(
        args.output_dir / "roundT_pressureGate_fp_component_extents.png",
        components,
        list(args.frames),
        fp_frames,
        args.minimum_points,
    )
    fp_components = [
        row for row in components
        if int(row["frame"]) in selected_fp
        and row.get("zone", "core") == "core"
        and int(row.get("point_count", 0)) >= 1000
    ]
    fp_components = sorted(fp_components, key=lambda row: (int(row["frame"]), -int(row["point_count"])))
    summary = {
        "format": "roundT_pressureGate_fp_visual_inspection_v1",
        "scope": "OFFLINE_VISUAL_GEOMETRIC_EVIDENCE_NOT_RUNTIME",
        "source_id": args.source_id,
        "frames_rendered": list(args.frames),
        "baseline_v3_fp_frames_in_render": selected_fp,
        "minimum_points_rendered": args.minimum_points,
        "png": str(args.output_dir / "roundT_pressureGate_fp_component_extents.png"),
        "fp_components": [component_brief(row) for row in fp_components],
        "frame_context": plotted,
        "interpretation_ru": (
            "Три FP вызваны strong geometry gate: это длинные низкие CORE-компоненты "
            "на правой стороне сцены, протянутые вдоль пути. Они не проходят как "
            "model_v1_temporal и не попадают под текущие boundary-warning эвристики."
        ),
        "limitations": [
            "Rendered boxes are saved audit component extents, not raw point-level labels.",
            "No independent organizer GT boxes are available for these frames.",
            "This evidence does not change thresholds or runtime behavior.",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "roundT_pressureGate_fp_inspection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(args.output_dir), "fp_frames": selected_fp}, ensure_ascii=False))


if __name__ == "__main__":
    main()
