"""Render raw cloud + C++ axis/envelope/core output for Stage-5 validation.

The renderer consumes only stored C++ node JSON and raw XYZ.  It deliberately
does not select rails or classify any point.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SAMPLES = (1049, 1054, 10000, 10005)
MANUAL_REVIEW_SAMPLES = (1054, 10000)
MANUAL_REVIEW_STATIONS = (6.0, 14.0, 22.0, 30.0)


def draw_envelope(ax: plt.Axes, pairs: list[dict], bounds: list[float]) -> None:
    if len(pairs) < 2:
        return
    left_bound, right_bound = bounds[:2]
    center = np.asarray([[(a + b) / 2.0 for a, b in zip(pair["left_xyz"], pair["right_xyz"])] for pair in pairs])
    rail_left = np.asarray([pair["left_xyz"] for pair in pairs])
    for a, b, side in zip(center, center[1:], rail_left):
        direction = b[:2] - a[:2]
        length = np.linalg.norm(direction)
        if length == 0:
            continue
        normal = np.array([direction[1], -direction[0]]) / length
        if np.dot(normal, side[:2] - a[:2]) < 0:
            normal = -normal
        corners = np.vstack((a[:2] + normal * left_bound, a[:2] + normal * right_bound,
                             b[:2] + normal * right_bound, b[:2] + normal * left_bound,
                             a[:2] + normal * left_bound))
        ax.plot(corners[:, 0], -corners[:, 1], color="#f6f6f6", lw=.7, alpha=.85)


def draw_method(ax: plt.Axes, raw: np.ndarray, item: dict, method: str) -> None:
    cpp = item["cpp"]
    pairs = cpp.get("rail_pairs_source_xyz", [])
    color = "#4ea8de" if method == "baseline" else "#e63946"
    shown = raw[::25]
    ax.scatter(shown[:, 0], -shown[:, 1], s=.2, color="#8996a3", alpha=.23, linewidths=0)
    core = np.asarray(cpp.get("core_source_indices", []), dtype=np.int64)
    if core.size:
        ax.scatter(raw[core, 0], -raw[core, 1], s=.5, color="#ff3f58", alpha=.7, linewidths=0, label="C++ CORE returns")
    if pairs:
        left, right = np.asarray([pair["left_xyz"] for pair in pairs]), np.asarray([pair["right_xyz"] for pair in pairs])
        center = (left + right) / 2.0
        ax.plot(left[:, 0], -left[:, 1], color=color, lw=1.0, alpha=.9)
        ax.plot(right[:, 0], -right[:, 1], color=color, lw=1.0, alpha=.9)
        ax.plot(center[:, 0], -center[:, 1], color="#ffd34f", lw=1.7, label="C++ CurveRailAxis")
        draw_envelope(ax, pairs, cpp["core_bounds_source_axis"])
        ax.scatter([center[0, 0], center[-1, 0]], [-center[0, 1], -center[-1, 1]], s=22, marker="|", color="#65ed9c", label="support boundaries")
    support = item["support"]
    title = f"{method}: {cpp.get('curve_axis_status')}\n{support['status']}"
    if support["status"] == "NO_GEOMETRIC_SUPPORT":
        title += f" · {support['reason']}"
    ax.set_title(title, fontsize=9)
    ax.set(xlim=(-5, 4), ylim=(0, 85), xlabel="X source units", ylabel="forward ≈ −Y source units")
    ax.grid(alpha=.16)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output exists: {args.output}")
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    by_method = {method: {item["index"]: item for item in values} for method, values in data["results"].items()}
    args.output.mkdir(parents=True)
    manifest: list[dict] = []
    for index in SAMPLES:
        raw = np.fromfile(args.raw_dir / f"frame_{index:05d}.xyzf", dtype="<f4").reshape(-1, 3)
        figure, axes = plt.subplots(1, 2, figsize=(13, 7), sharex=True, sharey=True, constrained_layout=True)
        for axis, method in zip(axes, ("baseline", "development_candidate")):
            draw_method(axis, raw, by_method[method][index], method)
        figure.suptitle(
            f"new_data {index}: raw source returns + exact C++ output\n"
            "Grey raw is display-decimated; red points are C++ CORE; white outline is C++ core envelope. "
            "Support is geometry only, not proof of visible/clear space.", fontsize=10)
        handles, labels = axes[1].get_legend_handles_labels()
        figure.legend(handles, labels, loc="lower center", ncol=3, fontsize=8)
        output = args.output / f"new_data_{index:05d}_cpp_comparison.png"
        figure.savefig(output, dpi=210)
        plt.close(figure)
        manifest.append({"index": index, "image": output.name, "methods": list(by_method),
                         "source": "exact C++ node JSON plus raw XYZ; no viewer-side detector"})
    manual_dir = args.output / "manual_raw_sections"
    manual_dir.mkdir()
    manual_template: list[dict] = []
    for index in MANUAL_REVIEW_SAMPLES:
        raw = np.fromfile(args.raw_dir / f"frame_{index:05d}.xyzf", dtype="<f4").reshape(-1, 3)
        figure, axes = plt.subplots(1, len(MANUAL_REVIEW_STATIONS), figsize=(16, 4), sharey=True, constrained_layout=True)
        for station, axis in zip(MANUAL_REVIEW_STATIONS, axes):
            section = raw[np.abs(-raw[:, 1] - station) <= .5]
            axis.scatter(section[:, 0], section[:, 2], s=2, color="#277da1", alpha=.6, linewidths=0)
            axis.set(title=f"s≈{station:.0f} m", xlabel="X source units", xlim=(-4, 4), ylim=(-3, 1))
            axis.grid(alpha=.2)
            manual_template.append({
                "frame_index": index, "station_s_m_assumed": station, "section_half_width_m_assumed": .5,
                "required_marks": ["left_rail_head_source_return", "right_rail_head_source_return"],
                "mark_rule": "Pick exact raw source returns at the two rail-head crowns without viewing AutoRails/C++ pair overlays.",
                "status": "UNMARKED",
            })
        axes[0].set_ylabel("Z source units")
        figure.suptitle(f"new_data {index}: raw-only cross sections for independent rail review (no detector overlay)")
        figure.savefig(manual_dir / f"new_data_{index:05d}_raw_sections.png", dpi=210)
        plt.close(figure)
    (manual_dir / "manual_rail_markup_template.json").write_text(
        json.dumps({"format": "stage_5_independent_rail_markup_template_v1", "marks": manual_template}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "README.md").write_text(
        "# C++ axis validation visuals\n\n"
        "Each panel uses the matching C++ `curve_envelope_node` result from the validation manifest. Grey dots are only display decimation of raw source returns; selected rail pairs, axis, core envelope and core returns come from C++ JSON. "
        "The outlined envelope exists only between its first and last selected pairs. It is geometric support, not evidence that every point of space was observed or is clear.\n\n"
        "`manual_raw_sections/` has raw-only cross sections for frames 1054 and 10000. The template requires two exact raw source returns (left/right rail-head crown) per listed section, selected without viewing detector overlays. Until those marks exist, no axis-error metric is valid.\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
