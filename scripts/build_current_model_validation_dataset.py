"""Build the validation dataset used for the submitted current model.

This is a thin, fixed-protocol wrapper around build_synthetic_recall_dataset.py.
It creates the project's own synthetic validation dataset used to probe the
submitted baseline_v3 pipeline; it does not train models and does not change
runtime defaults.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


DEFAULT_DATASET_VERSION = "current_model_validation_synthetic_no100_v1"
DEFAULT_SOURCE_WINDOW = "doubleT_obstacle:0:8"
DEFAULT_SPLIT_POLICY = "all_train"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_stream_cli() -> str:
    docker_cli = Path("/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli")
    if docker_cli.exists():
        return str(docker_cli)
    return "curve_pipeline_stream_cli"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=repo_root(),
                        help="project root containing dataset/for_hackathon")
    parser.add_argument("--output", type=Path,
                        default=Path("artefacts/current_model_validation/synthetic_no100"),
                        help="output directory for generated manifest, labels and component rows")
    parser.add_argument("--stream-cli", default=default_stream_cli(),
                        help="curve_pipeline_stream_cli path inside the active runtime/container")
    parser.add_argument("--source-window", default=DEFAULT_SOURCE_WINDOW,
                        help="fixed SOURCE:FIRST:COUNT window used for the validation dataset")
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET_VERSION)
    parser.add_argument("--split-policy", default=DEFAULT_SPLIT_POLICY,
                        choices=("all_train",),
                        help="fixed policy for this submitted validation dataset")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    builder = root / "scripts" / "build_synthetic_recall_dataset.py"
    if not builder.exists():
        raise FileNotFoundError(f"missing builder: {builder}")

    command = [
        sys.executable,
        str(builder),
        "--root", str(root),
        "--output", str(output),
        "--stream-cli", args.stream_cli,
        "--source-window", args.source_window,
        "--split-policy", args.split_policy,
        "--dataset-version", args.dataset_version,
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
