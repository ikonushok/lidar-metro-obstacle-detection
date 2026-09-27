"""Prepare saved new_data probe XYZ for a read-only AutoRails geometry review."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"Output exists: {args.output}")
    records = [json.loads(line) for line in (args.probe / "frames.jsonl").read_text(encoding="utf-8").splitlines()]
    args.output.mkdir(parents=True)
    exported: list[dict] = []
    hashes: dict[str, str] = {}
    for record in records:
        index = record["index"]
        source = args.probe / f"frame_{index:05d}.npy"
        xyz = np.load(source)
        if xyz.ndim != 2 or xyz.shape[1] != 3 or xyz.dtype != np.float32:
            raise ValueError(f"Unexpected XYZ export: {source}")
        if not np.isfinite(xyz).all() or np.any(np.all(xyz == 0, axis=1)):
            raise ValueError(f"Export is not finite non-zero XYZ: {source}")
        destination = args.output / f"frame_{index:05d}.xyzf"
        xyz.tofile(destination)
        hashes[str(index)] = hashlib.sha256(destination.read_bytes()).hexdigest()
        exported.append(
            {
                "index": index,
                "bag_offset_seconds": record["bag_offset_seconds"],
                "header_timestamp_ns": str(record["input"]["header_ns"]),
                "input": {"frame": record["input"]["frame"], "nonzero_finite": int(xyz.shape[0])},
            }
        )
    serialized = "\n".join(json.dumps(record, separators=(",", ":")) for record in exported) + "\n"
    (args.output / "frames.jsonl").write_text(serialized, encoding="utf-8")
    summary = {
        "dataset": "new_data",
        "scope": "SAVED_PROBE_READ_ONLY_GEOMETRY_REVIEW_NOT_CALIBRATION_OR_ODOMETRY",
        "frame_count": len(exported),
        "first_index": exported[0]["index"],
        "last_index": exported[-1]["index"],
        "source_frame": "hesai_lidar",
        "source_mutations": 0,
        "safety_decision_permitted": False,
        "clear_decision_permitted": False,
        "source_probe": str(args.probe).replace("\\", "/"),
        "xyzf_sha256": hashes,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(args.probe / "summary.json", args.output / "source_probe_summary.json")


if __name__ == "__main__":
    main()
