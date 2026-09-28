import json
import signal
import statistics
import sys
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percent / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def main():
    topic = sys.argv[1]
    expected = int(sys.argv[2])
    timeout_s = float(sys.argv[3])

    messages = []
    started = time.monotonic()

    # A signal must stop the spin loop before destroying its ROS context.
    # rclpy's default SIGTERM handler can invalidate a wait set mid-spin.
    shutdown_reason = None

    def request_shutdown(signum, _frame):
        nonlocal shutdown_reason
        shutdown_reason = signal.Signals(signum).name

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    node = rclpy.create_node("headless_ros2_cpp_perf_collector")

    def callback(msg):
        messages.append({"received_monotonic_s": time.monotonic(), "data": msg.data})

    node.create_subscription(String, topic, callback, 1000)
    deadline = started + timeout_s
    try:
        while (rclpy.ok() and shutdown_reason is None
               and time.monotonic() < deadline and len(messages) < expected):
            rclpy.spin_once(node, timeout_sec=0.1)
    except ExternalShutdownException:
        shutdown_reason = "ExternalShutdownException"

    finished = time.monotonic()
    if shutdown_reason is None and len(messages) < expected:
        shutdown_reason = "timeout" if finished >= deadline else "context_shutdown"
    try:
        node.destroy_node()
    except Exception:
        pass
    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception:
        pass

    parsed = []
    processing = []
    status_counts = {}
    reason_counts = {}
    candidate_true = 0
    for index, item in enumerate(messages):
        try:
            payload = json.loads(item["data"])
        except Exception as exc:
            payload = {"parse_error": str(exc), "raw": item["data"]}
        payload["_collector_index"] = index
        payload["_received_monotonic_offset_s"] = item["received_monotonic_s"] - started
        parsed.append(payload)
        value = payload.get("processing_ms")
        if isinstance(value, (int, float)):
            processing.append(float(value))
        status = payload.get("status", "MISSING")
        reason = payload.get("reason", "MISSING")
        status_counts[status] = status_counts.get(status, 0) + 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if payload.get("intrusion_candidate_present") is True:
            candidate_true += 1

    summary = {
        "format": "headless_ros2_cpp_performance_v1",
        "runtime_path": "ros2_bag_play_to_pointcloud2_to_curve_envelope_node_to_json",
        "player_or_http_in_path": False,
        "expected_messages": expected,
        "received_messages": len(messages),
        "collector_wall_seconds": finished - started,
        "collector_effective_output_hz": len(messages) / (finished - started) if finished > started else None,
        "processing_ms": {
            "count": len(processing),
            "p50": percentile(processing, 50),
            "p95": percentile(processing, 95),
            "p99": percentile(processing, 99),
            "max": max(processing) if processing else None,
            "mean": statistics.fmean(processing) if processing else None,
        },
        "status_counts": status_counts,
        "reason_counts": reason_counts,
        "intrusion_candidate_true_count": candidate_true,
        "first_header_timestamp_ns": parsed[0].get("header_timestamp_ns") if parsed else None,
        "last_header_timestamp_ns": parsed[-1].get("header_timestamp_ns") if parsed else None,
        "collector_shutdown_reason": shutdown_reason,
    }

    print(json.dumps({"summary": summary, "messages": parsed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
