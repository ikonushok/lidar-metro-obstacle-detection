"""Strictly combine non-overlapping source-part C++ catalog shards."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil


def load(path: Path) -> dict:
    return json.loads((path / "catalog_manifest.json").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shard", required=True, type=Path, action="append")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    manifests = [(path, load(path)) for path in args.shard]
    reference = manifests[0][1]
    required = ("format", "compute_backend", "rail_selection_method", "source_archive", "axis_contract", "units")
    for _, manifest in manifests[1:]:
        if any(manifest.get(key) != reference.get(key) for key in required):
            raise ValueError("shards do not have the same protected catalog contract")
    parts = [part for _, manifest in manifests for part in manifest["parts"]]
    parts.sort(key=lambda part: part["part_index"])
    if len({part["part_index"] for part in parts}) != len(parts):
        raise ValueError("duplicated source part across shards")
    if parts[0]["first_index"] != 0 or parts[-1]["last_index"] != 11270:
        raise ValueError("shards do not cover the complete expected new_data interval")
    if any(current["last_index"] + 1 != following["first_index"] for current, following in zip(parts, parts[1:])):
        raise ValueError("shard parts are not contiguous")
    args.output.mkdir(parents=True)
    target_parts = args.output / "parts"
    target_parts.mkdir()
    for shard_path, manifest in manifests:
        for part in manifest["parts"]:
            source = shard_path / part["catalog_file"]
            target = target_parts / source.name
            if target.exists():
                raise FileExistsError(target)
            shutil.copy2(source, target)
    status_counts, reason_counts = Counter(), Counter()
    for _, manifest in manifests:
        status_counts.update(manifest["status_counts"])
        reason_counts.update(manifest["reason_counts"])
    merged = dict(reference)
    merged.update({
        "frame_interval_inclusive": [0, 11270], "frame_count": sum(part["frame_count"] for part in parts),
        "source_part_count": len(parts), "parts": parts, "status_counts": dict(status_counts),
        "reason_counts": dict(reason_counts),
        "core_returns_total": sum(manifest["core_returns_total"] for _, manifest in manifests),
        "wall_processing_ms_total": sum(manifest["wall_processing_ms_total"] for _, manifest in manifests),
        "node_processing_ms_total_for_supported_frames": sum(manifest["node_processing_ms_total_for_supported_frames"] for _, manifest in manifests),
        "node_processing_frame_count": sum(manifest["node_processing_frame_count"] for _, manifest in manifests),
        "merged_from_shards": [str(path) for path, _ in manifests],
    })
    (args.output / "catalog_manifest.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "window_index.json").write_text(json.dumps(parts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "frames": merged["frame_count"], "parts": len(parts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
