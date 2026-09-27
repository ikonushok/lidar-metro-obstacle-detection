"""Render a synchronized baseline-vs-candidate GIF from a visual-only frame sequence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import numpy as np


def draw_axis(axis, pairs, color):
    if not pairs:
        return
    left = np.asarray([pair["left_xyz"] for pair in pairs])
    right = np.asarray([pair["right_xyz"] for pair in pairs])
    center = (left + right) / 2
    for side in (left, right):
        axis.plot(side[:, 0], -side[:, 1], color=color, lw=1.1)
    axis.plot(center[:, 0], -center[:, 1], color=color, lw=2.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fps", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output exists: {args.output}")
    sequence = json.loads(args.sequence.read_text(encoding="utf-8"))["frames"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 7), sharex=True, sharey=True, constrained_layout=True)

    def frame(index: int):
        record = sequence[index]
        raw = np.fromfile(record["file"], dtype="<f4").reshape(-1, 3)[::20]
        for axis, method, color, name in zip(axes, (record["baseline"], record["candidate"]), ("#0077b6", "#d00000"), ("baseline", "candidate")):
            axis.clear()
            axis.scatter(raw[:, 0], -raw[:, 1], s=.35, c="#6c757d", alpha=.25, linewidths=0)
            draw_axis(axis, method["rail_pairs"], color)
            axis.set(title=f"{name}: {method['status']}\n{method['reason']}", xlim=(-5, 5), ylim=(0, 40), xlabel="X source units")
            axis.grid(alpha=.2)
        axes[0].set_ylabel("forward approx. −Y source units")
        figure.suptitle(f"new_data frame {record['index']} | same raw frame in both panels | grey=raw display-decimated")

    animation = FuncAnimation(figure, frame, frames=len(sequence), interval=1000 / args.fps, repeat=True)
    animation.save(args.output, writer=PillowWriter(fps=args.fps), dpi=130)
    plt.close(figure)
    print(args.output)


if __name__ == "__main__":
    main()
