"""Audit raw geometric CORE returns without the model filter for one archive source."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sqlite3
import struct
import subprocess

from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from archive_bag_frames import ArchiveBagFrames
from cloud_input import inspect_cloud
from stage_2_player import encode_xyz_frame, frame_record
from train_noise_classifier import connected_components, component_features


class ExtractedBagFrames:
    """Reads one extracted single-part rosbag2 directory."""

    def __init__(self, bag_dir: Path, dataset_id: str):
        self.bag_dir = bag_dir
        self.dataset_id = dataset_id
        databases = sorted(bag_dir.glob("*.db3"))
        if len(databases) != 1:
            raise ValueError(f"Expected exactly one .db3 in {bag_dir}")
        self.database = databases[0]
        with sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            topics = connection.execute(
                "select id,name,type,serialization_format from topics"
            ).fetchall()
            point_topics = [
                row for row in topics
                if row[2] == "sensor_msgs/msg/PointCloud2" and row[3] == "cdr"
            ]
            if len(point_topics) != 1:
                raise ValueError("Bag must contain exactly one PointCloud2/cdr topic")
            self.topic_id, self.topic_name, _type, _serialization = point_topics[0]
            self.count = connection.execute(
                "select count(*) from messages where topic_id=?", (self.topic_id,)
            ).fetchone()[0]
            first = connection.execute(
                "select timestamp from messages where topic_id=? order by timestamp,id limit 1",
                (self.topic_id,),
            ).fetchone()
            if first is None:
                raise ValueError("Bag contains no PointCloud2 messages")
            self.first_ns = int(first[0])
        self.lookup = list(range(self.count))

    def close(self) -> None:
        return None

    def frame(self, index: int):
        if not 0 <= index < self.count:
            raise IndexError("Frame outside dataset")
        with sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            row = connection.execute(
                "select timestamp,data from messages where topic_id=? "
                "order by timestamp,id limit 1 offset ?",
                (self.topic_id, index),
            ).fetchone()
        if row is None:
            raise IndexError("Frame outside dataset")
        stamp, data = row
        stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
        record = frame_record(index, stamp, stats, xyz, self.first_ns, "")
        record.update(dataset_id=self.dataset_id, source_part=str(self.database), source_topic=self.topic_name)
        return record, encode_xyz_frame(xyz)


def stream_result(process: subprocess.Popen[bytes], raw: bytes, source_id: str, frame: int) -> dict:
    process.stdin.write(struct.pack("<Q", len(raw) // 12))
    process.stdin.write(raw)
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError(
            f"{source_id} frame {frame}: C++ stream stopped: "
            + process.stderr.read().decode(errors="replace")[-2000:]
        )
    return json.loads(line)


def segments_from_rail_pairs(pairs: list[dict]) -> list[dict]:
    segments = []
    for left, right in zip(pairs, pairs[1:]):
        ax = (left["left_xyz"][0] + left["right_xyz"][0]) * 0.5
        ay = (left["left_xyz"][1] + left["right_xyz"][1]) * 0.5
        bx = (right["left_xyz"][0] + right["right_xyz"][0]) * 0.5
        by = (right["left_xyz"][1] + right["right_xyz"][1]) * 0.5
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            continue
        segments.append(
            {
                "ax": ax,
                "ay": ay,
                "tx": dx / length,
                "ty": dy / length,
                "length": length,
                "s0": float(left["source_s_m"]),
                "s1": float(right["source_s_m"]),
            }
        )
    return segments


def project_s(raw: bytes, index: int, segments: list[dict]) -> float | None:
    x, y, _z = struct.unpack_from("<fff", raw, index * 12)
    best_distance = math.inf
    best_s = None
    for segment in segments:
        dx, dy = x - segment["ax"], y - segment["ay"]
        station = min(max(dx * segment["tx"] + dy * segment["ty"], 0.0), segment["length"])
        nx = segment["ax"] + segment["tx"] * station
        ny = segment["ay"] + segment["ty"] * station
        distance = math.hypot(x - nx, y - ny)
        if distance < best_distance:
            best_distance = distance
            fraction = 0.0 if segment["length"] <= 0.0 else station / segment["length"]
            best_s = segment["s0"] + fraction * (segment["s1"] - segment["s0"])
    return best_s


def component_summary(raw: bytes, component: list[int], segments: list[dict], zone: str) -> dict:
    features = component_features(raw, component)
    stations = [project_s(raw, index, segments) for index in component]
    stations = [value for value in stations if value is not None and math.isfinite(value)]
    xs, ys, zs = zip(*(struct.unpack_from("<fff", raw, index * 12) for index in component))
    distances = [math.sqrt(x * x + y * y + z * z) for x, y, z in zip(xs, ys, zs)]
    return {
        "zone": zone,
        "point_count": len(component),
        "min_s_m": min(stations) if stations else None,
        "max_s_m": max(stations) if stations else None,
        "nearest_distance_m": min(distances),
        "centroid_xyz": [
            sum(xs) / len(component),
            sum(ys) / len(component),
            sum(zs) / len(component),
        ],
        "extent_xyz_m": features[1:4],
    }


def audit(args: argparse.Namespace) -> dict:
    if args.bag_dir is not None:
        source = ExtractedBagFrames(args.bag_dir, args.source_id)
        source_label = str(args.bag_dir)
    else:
        source = ArchiveBagFrames(args.archive, args.prefix, args.source_id)
        source_label = str(args.archive)
    process = subprocess.Popen(
        [str(args.stream_cli), str(args.rail_forward_min_m)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    frame_rows = []
    component_rows = []
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    try:
        final = len(source.lookup) - 1 if args.last is None else min(args.last, len(source.lookup) - 1)
        for frame in range(args.first, final + 1):
            record, raw = source.frame(frame)
            result = stream_result(process, raw, args.source_id, frame)
            status_counts[result.get("status", "<missing>")] += 1
            reason_counts[result.get("reason", "<missing>")] += 1
            if result.get("curve_axis_status") != "CURVE_AXIS_SUPPORTED":
                frame_rows.append(
                    {
                        "frame": frame,
                        "bag_offset_seconds": record["bag_offset_seconds"],
                        "status": result.get("status"),
                        "reason": result.get("reason"),
                        "raw_core_points_0_60m": 0,
                        "component_count_0_60m": 0,
                    }
                )
                continue
            segments = segments_from_rail_pairs(result.get("rail_pairs_source_xyz", []))
            zone_indices = {"core": result.get("core_source_indices", [])}
            if args.include_margin:
                zone_indices["margin"] = result.get("margin_source_indices", [])
            limited_by_zone = {}
            components_by_zone = {}
            for zone, source_indices in zone_indices.items():
                limited_by_zone[zone] = [
                    index
                    for index in source_indices
                    if (s := project_s(raw, index, segments)) is not None
                    and args.min_s_m <= s <= args.max_s_m
                ]
                components_by_zone[zone] = connected_components(
                    raw, limited_by_zone[zone], args.connectivity_radius_m
                )
            limited_core = limited_by_zone["core"]
            limited_margin = limited_by_zone.get("margin", [])
            core_components = [
                component
                for component in components_by_zone["core"]
                if len(component) >= args.min_component_points
            ]
            margin_components = [
                component
                for component in components_by_zone.get("margin", [])
                if len(component) >= args.min_component_points
            ]
            reportable_components = core_components
            all_summaries = [
                {"frame": frame, **component_summary(raw, component, segments, "core")}
                for component in core_components
            ] + [
                {"frame": frame, **component_summary(raw, component, segments, "margin")}
                for component in margin_components
            ]
            summaries = [
                summary for summary in all_summaries if summary["zone"] == "core"
            ]
            component_rows.extend(all_summaries)
            frame_rows.append(
                {
                    "frame": frame,
                    "bag_offset_seconds": record["bag_offset_seconds"],
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                    "raw_core_points_0_60m": len(limited_core),
                    "raw_margin_points_0_60m": len(limited_margin),
                    "component_count_0_60m": len(reportable_components),
                    "margin_component_count_0_60m": len(margin_components),
                    "largest_component_points": max(
                        (item["point_count"] for item in summaries), default=0
                    ),
                    "largest_margin_component_points": max(
                        (item["point_count"] for item in all_summaries if item["zone"] == "margin"),
                        default=0,
                    ),
                    "nearest_component_distance_m": min(
                        (item["nearest_distance_m"] for item in summaries), default=None
                    ),
                }
            )
            if (frame + 1) % 100 == 0:
                print(json.dumps({"processed": frame + 1, "frames": final + 1}), flush=True)
    finally:
        source.close()
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    positive_frames = [row for row in frame_rows if row["component_count_0_60m"] > 0]
    largest_frames = sorted(
        positive_frames, key=lambda row: row.get("largest_component_points", 0), reverse=True
    )[:20]
    nearest_components = sorted(component_rows, key=lambda row: row["nearest_distance_m"])[:20]
    largest_components = sorted(component_rows, key=lambda row: row["point_count"], reverse=True)[:20]
    summary = {
        "format": "raw_geometric_core_audit_v1",
        "source_id": args.source_id,
        "source": source_label,
        "frame_range_inclusive": [args.first, frame_rows[-1]["frame"] if frame_rows else args.first],
        "frame_count": len(frame_rows),
        "range_s_m": [args.min_s_m, args.max_s_m],
        "model_filter": "disabled",
        "legacy_noise_filter_for_decision": "ignored; audit uses raw core_source_indices only",
        "connectivity_radius_m": args.connectivity_radius_m,
        "min_component_points": args.min_component_points,
        "status_counts": dict(status_counts),
        "reason_counts": dict(reason_counts),
        "frames_with_raw_core_points": sum(row["raw_core_points_0_60m"] > 0 for row in frame_rows),
        "frames_with_components": len(positive_frames),
        "total_raw_core_points_0_60m": sum(row["raw_core_points_0_60m"] for row in frame_rows),
        "total_components_0_60m": len(component_rows),
        "component_point_count_histogram": dict(
            Counter(
                "22-49"
                if row["point_count"] < 50
                else "50-99"
                if row["point_count"] < 100
                else "100-249"
                if row["point_count"] < 250
                else "250+"
                for row in component_rows
            )
        ),
        "largest_frame_examples": largest_frames,
        "nearest_component_examples": nearest_components,
        "largest_component_examples": largest_components,
        "limitations": [
            "This is a noisy geometric upper bound, not a final detector decision.",
            "No organizer GT boxes/intervals are available, so components are possible obstacles, not labelled TP.",
            "UNKNOWN frames are not CLEAR and contribute no supported-axis geometric count here.",
        ],
    }
    return {"summary": summary, "frames": frame_rows, "components": component_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--bag-dir", type=Path)
    parser.add_argument("--prefix")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--stream-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--last", type=int)
    parser.add_argument("--rail-forward-min-m", type=float, default=2.0)
    parser.add_argument("--min-s-m", type=float, default=0.0)
    parser.add_argument("--max-s-m", type=float, default=60.0)
    parser.add_argument("--connectivity-radius-m", type=float, default=0.25)
    parser.add_argument("--min-component-points", type=int, default=22)
    parser.add_argument("--include-margin", action="store_true")
    args = parser.parse_args()
    if (args.archive is None) == (args.bag_dir is None):
        parser.error("Specify exactly one of --archive or --bag-dir")
    if args.archive is not None and not args.prefix:
        parser.error("--archive requires --prefix")
    result = audit(args)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "frames.json").write_text(
        json.dumps(result["frames"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "components.json").write_text(
        json.dumps(result["components"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
