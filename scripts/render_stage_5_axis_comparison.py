"""Render baseline/candidate rail-pair overlays for a fixed Stage 5 comparison."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


def raw_points(record: dict, raw_dir: Path) -> np.ndarray:
    if record["dataset"] == "new_data":
        source = raw_dir / f"frame_{record['index']:05d}.xyzf"
    else:
        source = Path(record["file"])
    return np.fromfile(source, dtype="<f4").reshape(-1, 3)


def draw_pairs(axis: plt.Axes, pairs: list[dict], color: str, style: str, label: str) -> None:
    if not pairs:
        return
    left = np.asarray([pair["left_xyz"] for pair in pairs])
    right = np.asarray([pair["right_xyz"] for pair in pairs])
    center = (left + right) / 2
    # Source convention in this dataset: forward distance is approximately -Y.
    axis.plot(left[:, 0], -left[:, 1], color=color, lw=1.1, ls=style, alpha=.95)
    axis.plot(right[:, 0], -right[:, 1], color=color, lw=1.1, ls=style, alpha=.95)
    axis.plot(center[:, 0], -center[:, 1], color=color, lw=1.7, ls=style, alpha=.95, label=label)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output exists: {args.output}")
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    records = [record for record in comparison["records"] if not record.get("synthetic")]
    args.output.mkdir(parents=True)
    manifest: list[dict] = []

    for record in records:
        raw = raw_points(record, args.raw_dir)
        # Decimation is display-only; axis points are never decimated.
        raw = raw[::20]
        figure, axis = plt.subplots(figsize=(7, 8), constrained_layout=True)
        axis.scatter(raw[:, 0], -raw[:, 1], s=.3, c="#6c757d", alpha=.25, linewidths=0, label="raw returns (display decimated)")
        baseline_pairs = record["baseline"].get("rail_pairs_source_xyz", [])
        candidate_pairs = record["candidate"].get("rail_pairs_source_xyz", [])
        draw_pairs(axis, baseline_pairs, "#0077b6", "-", "baseline paired ridges / center")
        draw_pairs(axis, candidate_pairs, "#d00000", "--", "candidate paired ridges / center")
        all_pairs = baseline_pairs + candidate_pairs
        max_supported_forward = max(
            [-point[1] for pair in all_pairs for point in (pair["left_xyz"], pair["right_xyz"])],
            default=10,
        )
        delta = record["candidate"]["supported_length_m"] - record["baseline"]["supported_length_m"]
        axis.set(
            title=(f"{record['id']} | baseline {record['baseline']['status']}; "
                   f"candidate {record['candidate']['status']} | Δ supported length {delta:+.2f} m"),
            xlabel="X source units", ylabel="forward approx. −Y source units",
            xlim=(-5, 5), ylim=(0, max_supported_forward + 4), aspect="auto",
        )
        axis.grid(alpha=.2)
        handles = [
            Line2D([0], [0], color="#6c757d", marker=".", lw=0, label="raw returns (decimated for display)"),
            Line2D([0], [0], color="#0077b6", lw=1.5, label="baseline: rail-pair sides + center"),
            Line2D([0], [0], color="#d00000", lw=1.5, ls="--", label="candidate: rail-pair sides + center"),
        ]
        axis.legend(handles=handles, loc="upper right", fontsize=8)
        output_png = args.output / f"{record['id']}_top_view.png"
        figure.savefig(output_png, dpi=220)
        plt.close(figure)
        manifest.append({
            "id": record["id"], "image": output_png.name,
            "baseline_status": record["baseline"]["status"],
            "candidate_status": record["candidate"]["status"],
            "baseline_pair_count": len(baseline_pairs),
            "candidate_pair_count": len(candidate_pairs),
            "supported_length_delta_m": delta,
            "display_note": "Grey raw points are decimated only for display. Lines use exact selected source returns; an overlay shows selection/coverage, not calibrated axis error.",
        })
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (args.output / "README.md").write_text(
        "# Stage 5 visual comparison\n\n"
        "Open the `*_top_view.png` files at full resolution. Grey is the raw cloud (display-only decimation); blue solid is the baseline rail-pair path; red dashed is the candidate. "
        "A missing blue path means baseline returned `UNKNOWN`, not an empty cloud. Compare (1) whether red follows paired local ridges, (2) its start/end coverage, and (3) any visible jump to non-rail geometry. "
        "This is a selection/coverage review in unchanged source XYZ, not absolute calibration or a clearance verdict.\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
