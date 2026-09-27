"""Compare two curve_pipeline_stream_cli binaries on the same archive frames."""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
from pathlib import Path

from archive_bag_frames import ArchiveBagFrames


def start(command: str) -> subprocess.Popen:
    return subprocess.Popen(
        [command, "2.0", "--use-model-filter"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_frame(process: subprocess.Popen, raw: bytes) -> dict:
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(struct.pack("<Q", len(raw) // 12))
    process.stdin.write(raw)
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
        raise RuntimeError(f"stream stopped: {stderr[-1000:]}")
    return json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--left-cli", required=True)
    parser.add_argument("--right-cli", required=True)
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--source", default="new_data")
    parser.add_argument("--prefix", default="new_data")
    parser.add_argument("--archive-name", default="new_data")
    args = parser.parse_args()
    archive = args.root / "dataset/for_hackathon" / args.archive_name
    source = ArchiveBagFrames(archive, args.prefix, args.source)
    left = start(args.left_cli)
    right = start(args.right_cli)
    keys = [
        "status",
        "core_count",
        "reportable_core_count",
        "ignored_noise_count",
        "model_reportable_core_count",
        "model_ignored_noise_count",
        "reportable_core_source_indices",
        "ignored_noise_source_indices",
        "model_reportable_core_source_indices",
        "model_ignored_noise_source_indices",
    ]
    try:
        checked = min(args.frames, len(source.lookup))
        for frame in range(checked):
            _, raw = source.frame(frame)
            left_result = run_frame(left, raw)
            right_result = run_frame(right, raw)
            for key in keys:
                if left_result.get(key) != right_result.get(key):
                    raise AssertionError(
                        f"frame {frame} mismatch {key}: "
                        f"{left_result.get(key)!r} != {right_result.get(key)!r}"
                    )
        print(json.dumps({"checked_frames": checked, "status": "MATCH"}, ensure_ascii=False))
    finally:
        source.close()
        for process in (left, right):
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
