"""Publish one saved XYZ frame to the C++ node and verify its candidate JSON."""

import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import String


def cloud_from_xyzf(path: Path) -> PointCloud2:
    data = path.read_bytes()
    if not data or len(data) % 12:
        raise ValueError("XYZF must contain non-empty float32 XYZ triplets")
    cloud = PointCloud2()
    cloud.header.frame_id = "hesai_lidar"
    cloud.height = 1
    cloud.width = len(data) // 12
    cloud.is_bigendian = False
    cloud.is_dense = True
    cloud.point_step = 12
    cloud.row_step = cloud.width * cloud.point_step
    cloud.fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    cloud.data = data
    return cloud


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xyzf", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--noise-filter-mode", choices=("legacy", "baseline_v3_assist_score"), default="legacy",
                        help="legacy preserves this historical positive-fixture smoke; model parity has a separate checker")
    parser.add_argument("--rail-selection-method", choices=("baseline", "development_candidate"), default="development_candidate")
    parser.add_argument("--rail-forward-min-m", type=float, default=2.0)
    parser.add_argument("--forward-extension-method", choices=("tangent", "arc_limited", "arc_clamped"), default="tangent")
    parser.add_argument("--arc-extension-horizon-m", type=float, default=0.0)
    parser.add_argument("--min-arc-radius-m", type=float, default=60.0)
    parser.add_argument("--max-arc-turn-deg", type=float, default=8.0)
    parser.add_argument("--arc-fit-window-pairs", type=int, default=5)
    parser.add_argument("--expect-unknown", action="store_true",
                        help="publish one source return, which cannot support CurveRailAxis")
    args = parser.parse_args()
    command = [
        "ros2", "run", "lidar_mosmetro3d_cpp", "curve_envelope_node", "--ros-args",
        "-p", "input_topic:=/smoke/cloud", "-p", "output_topic:=/smoke/candidate",
        "-p", "source_frame:=hesai_lidar", "-p", f"compute_backend:={args.backend}",
        "-p", f"noise_filter_mode:={args.noise_filter_mode}",
        "-p", f"rail_selection_method:={args.rail_selection_method}",
        "-p", f"rail_forward_min_m:={args.rail_forward_min_m}",
        "-p", f"forward_extension_method:={args.forward_extension_method}",
        "-p", f"arc_extension_horizon_m:={args.arc_extension_horizon_m}",
        "-p", f"min_arc_radius_m:={args.min_arc_radius_m}",
        "-p", f"max_arc_turn_deg:={args.max_arc_turn_deg}",
        "-p", f"arc_fit_window_pairs:={args.arc_fit_window_pairs}",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    rclpy.init()
    node = rclpy.create_node("curve_envelope_smoke")
    received = []
    publisher = node.create_publisher(PointCloud2, "/smoke/cloud", qos_profile_sensor_data)
    node.create_subscription(String, "/smoke/candidate", lambda message: received.append(message.data), 10)
    try:
        cloud = cloud_from_xyzf(args.xyzf)
        if args.expect_unknown:
            cloud.width = 1
            cloud.row_step = cloud.point_step
            cloud.data = cloud.data[:cloud.point_step]

        def publish_until_result(expected_stamp: str):
            received.clear()
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                publisher.publish(cloud)
                rclpy.spin_once(node, timeout_sec=0.1)
                for message in received:
                    parsed = json.loads(message)
                    if parsed.get("header_timestamp_ns") == expected_stamp:
                        return parsed
            process_status = process.poll()
            stderr = process.stderr.read() if process_status is not None else ''
            raise TimeoutError(
                f"no candidate output from curve_envelope_node; process_status={process_status}; stderr={stderr[-2000:]}"
            )

        result = publish_until_result("0")
        if (not args.expect_unknown and args.noise_filter_mode == "baseline_v3_assist_score" and
                result.get("temporal_confirmation_enabled") is True and
                result.get("model_frame_intrusion_candidate_present") is True and
                result.get("intrusion_candidate_present") is False):
            cloud.header.stamp.nanosec = 1
            result = publish_until_result("1")

        assert result["system_status"] == "UNKNOWN"
        assert result["noise_filter_mode"] == args.noise_filter_mode
        assert result["runtime_transport"] == "ros2"
        assert result["safety_decision_permitted"] is False
        assert result["all_core_returns_are_intrusion_candidates"] is False
        assert result["compute_backend_requested"] == args.backend
        assert result["rail_selection_method"] == args.rail_selection_method
        assert result["rail_search_config"]["forward_min_m"] == args.rail_forward_min_m
        assert result["forward_extension_method"] == args.forward_extension_method
        assert result["arc_extension_horizon_m"] == args.arc_extension_horizon_m
        assert result["min_arc_radius_m"] == args.min_arc_radius_m
        assert result["max_arc_turn_deg"] == args.max_arc_turn_deg
        assert result["arc_fit_window_pairs"] == args.arc_fit_window_pairs
        assert result["source_frame"] == "hesai_lidar"
        if args.expect_unknown:
            assert result["status"] == "UNKNOWN"
            assert result["intrusion_candidate_present"] is None
            assert result["reportable_intrusion_candidate_present"] is None
            assert result["temporal_confirmation_status"] == "RESET_UNKNOWN"
            assert result["model_frame_intrusion_candidate_present"] is None
            assert result["model_temporal_confirmed_intrusion_candidate_present"] is None
            assert result["raw_core_return_present"] is None
            assert result["margin_return_present"] is None
            assert result["curve_axis_polyline_source_xyz"] == []
            assert result["rail_pairs_source_xyz"] == []
            assert result["core_bounds_source_axis"] is None
            assert result["expanded_bounds_source_axis"] is None
            assert result["core_envelope_wireframe_source_xyz"] == []
            assert result["expanded_envelope_wireframe_source_xyz"] == []
            assert result["core_source_indices"] == []
            assert result["reportable_core_source_indices"] == []
            assert result["ignored_noise_source_indices"] == []
            assert result["margin_source_indices"] == []
        else:
            assert result["status"] == "OBSERVED_CORE_INTRUSION_CANDIDATE"
            assert result["reason"] == "ANY_REPORTABLE_CORE_COMPONENT_IS_INTRUSION_CANDIDATE"
            assert result["intrusion_candidate_present"] is True
            assert result["reportable_intrusion_candidate_present"] is True
            if args.noise_filter_mode == "baseline_v3_assist_score":
                assert result["model_frame_intrusion_candidate_present"] is True
                assert result["model_temporal_confirmed_intrusion_candidate_present"] is True
                assert result["model_temporal_consecutive_alarm_frames"] >= 2
                assert result["temporal_confirmation_status"] == "APPLIED_CONFIRMED"
            assert result["raw_core_return_present"] is True
            assert result["compute_backend_used"] == args.backend
            assert result["core_count"] > 0
            assert result["reportable_core_count"] > 0
            assert result["ignored_noise_count"] >= 0
            assert result["nearest_intrusion_source_index"] >= 0
            assert result["nearest_intrusion_distance_from_source_origin_m"] > 0.0
            assert len(result["nearest_intrusion_xyz"]) == 3
            assert result["nearest_reportable_intrusion_source_index"] >= 0
            assert result["nearest_reportable_intrusion_distance_from_source_origin_m"] > 0.0
            assert len(result["nearest_reportable_intrusion_xyz"]) == 3
            assert result["distance_reference"] == "SOURCE_ORIGIN"
            assert result["distance_units"] == "m_ASSUMED"
            assert result["noise_filter_status"] == "APPLIED"
            assert result["noise_filter_config"]["connectivity_radius_m"] == 0.25
            if args.noise_filter_mode == "legacy":
                assert result["noise_filter_config"]["min_reportable_core_points"] == 22
                assert result["noise_filter_config"]["max_axis_span_m"] == 1.0
                assert result["noise_filter_config"]["max_average_axis_distance_m"] == 1.2
            if args.forward_extension_method == "tangent":
                assert result["geometry_basis"] == "ASSUMED_CURVE_RAIL_AXIS_WITH_FORWARD_TANGENT_EXTRAPOLATION_SOURCE_XYZ"
                assert result["forward_extension_status"] == "TANGENT_APPLIED"
                assert result["forward_extrapolated"] is True
                assert result["envelope_forward_end_source_s_m"] == result["rail_search_config"]["forward_max_m"]
            else:
                assert result["forward_extension_status"] in {
                    "ARC_LIMITED_APPLIED", "ARC_HORIZON_DISABLED", "AT_FORWARD_LIMIT",
                    "INSUFFICIENT_ARC_SUPPORT", "COLLINEAR_ARC_SUPPORT",
                    "ARC_CLAMPED_APPLIED", "ARC_CLAMPED_TO_MAX_TURN",
                    "ARC_CLAMPED_REJECTED",
                }
                assert result["forward_extension_status"] != "TANGENT_APPLIED"
                if result["forward_extrapolated"]:
                    assert result["geometry_basis"] == "ASSUMED_CURVE_RAIL_AXIS_WITH_LIMITED_FORWARD_ARC_EXTRAPOLATION_SOURCE_XYZ"
                    assert result["forward_extension_applied_horizon_m"] <= args.arc_extension_horizon_m
                else:
                    assert result["geometry_basis"] == "ASSUMED_CURVE_RAIL_AXIS_FROM_SOURCE_XYZ"
            assert len(result["curve_axis_polyline_source_xyz"]) == result["rail_pair_count"]
            assert len(result["rail_pairs_source_xyz"]) == result["rail_pair_count"]
            assert result["core_bounds_source_axis"] == [-1.4, 1.4, 0.0, 3.7]
            assert result["expanded_bounds_source_axis"] == [-1.9, 1.9, -0.5, 4.2]
            expected_wireframe_lines = (result["rail_pair_count"] - 1) * 12
            for field in ("core_envelope_wireframe_source_xyz",
                          "expanded_envelope_wireframe_source_xyz"):
                wireframe = result[field]
                assert len(wireframe) == expected_wireframe_lines
                assert all(len(line) == 2 and all(len(point) == 3 for point in line)
                           for line in wireframe)
            assert len(result["core_source_indices"]) == result["core_count"]
            assert len(result["reportable_core_source_indices"]) == result["reportable_core_count"]
            assert len(result["ignored_noise_source_indices"]) == result["ignored_noise_count"]
            assert len(result["margin_source_indices"]) == result["margin_count"]
            assert result["nearest_intrusion_source_index"] in result["core_source_indices"]
            assert result["nearest_reportable_intrusion_source_index"] in result["reportable_core_source_indices"]
        print(json.dumps({
            'status': result['status'], 'reason': result['reason'],
            'rail_selection_method': result['rail_selection_method'],
            'rail_pair_count': result.get('rail_pair_count', 0),
            'core_count': result.get('core_count', 0),
            'unknown_count': result.get('unknown_count', result.get('point_count', 0)),
        }, sort_keys=True))
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"curve_envelope_node smoke: {error}", file=sys.stderr)
        raise
