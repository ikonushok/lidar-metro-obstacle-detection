"""Render three raw cross-sections for visual review of Stage 5 candidate rail pairs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output exists: {args.output}")
    payload = json.loads(args.comparison.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True)
    review: list[dict] = []
    for record in payload["records"]:
        if record["id"] not in {"new_data_1054", "new_data_10000"}:
            continue
        pairs = record["candidate"]["rail_pairs_source_xyz"]
        selections = [pairs[0], pairs[len(pairs) // 2], pairs[-1]]
        raw = np.fromfile(args.raw_dir / f"frame_{record['index']:05d}.xyzf", dtype="<f4").reshape(-1, 3)
        selected: list[dict] = []
        figure, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True, constrained_layout=True)
        for column, (pair, axis) in enumerate(zip(selections, axes)):
            station = pair["source_s_m"]
            section = raw[np.abs(-raw[:, 1] - station) <= 0.6]
            candidates = np.asarray([pair["left_xyz"], pair["right_xyz"]], dtype=np.float32)
            matches = [int(np.any(np.linalg.norm(raw - point, axis=1) < 1e-6)) for point in candidates]
            if matches != [1, 1]:
                raise ValueError(f"candidate pair is not two exact source returns: {record['id']} s={station}")
            axis.scatter(section[:, 0], section[:, 2], s=2, c="#277da1", alpha=.55, linewidths=0)
            axis.scatter(candidates[:, 0], candidates[:, 2], s=28, c="#e63946", marker="x", linewidths=1.4)
            axis.plot(candidates[:, 0], candidates[:, 2], c="#e63946", lw=.8)
            axis.set(title=f"s={station:.1f} m*", xlabel="X source units", xlim=(-4, 4), ylim=(-3, 1))
            axis.grid(alpha=.2)
            selected.append({"source_s_m": station, "left_xyz": pair["left_xyz"], "right_xyz": pair["right_xyz"],
                             "exact_source_return_matches": matches, "section_half_width_m_assumed": .6})
        axes[0].set_ylabel("Z source units")
        figure.suptitle(f"{record['id']}: raw cross-sections; red = candidate-assisted review anchors, not calibration")
        figure.savefig(args.output / f"{record['id']}_sections.png", dpi=180)
        plt.close(figure)
        review.append({"id": record["id"], "source_frame": record["source_frame"], "header_timestamp_ns": record["stamp"],
                       "coordinate_basis": "SOURCE_XYZ_UNCHANGED", "units": "m_ASSUMED", "selections": selected,
                       "interpretation": "VISUAL_RAIL_RIDGE_REVIEW_NOT_INDEPENDENT_GROUND_TRUTH_OR_CALIBRATION"})
    (args.output / "rail_section_review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(review, indent=2))


if __name__ == "__main__":
    main()
