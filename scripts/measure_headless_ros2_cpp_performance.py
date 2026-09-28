import argparse
import json
import re
import statistics
import subprocess
import threading
import time
from pathlib import Path


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, **kwargs)


def parse_percent(value):
    if not value:
        return None
    return float(value.strip().replace("%", ""))


def parse_mem_mib(mem_usage):
    if not mem_usage:
        return None
    used = mem_usage.split("/")[0].strip()
    match = re.match(r"^([0-9.]+)\s*([KMG]?i?)B$", used)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit in ("Gi", "G"):
        return value * 1024.0
    if unit in ("Mi", "M"):
        return value
    if unit in ("Ki", "K"):
        return value / 1024.0
    return value / 1048576.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="lidar-detector")
    parser.add_argument("--topic", default="/stage_3/curve_envelope_candidate")
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--read-ahead-queue-size", type=int, default=20)
    parser.add_argument("--expected-messages", type=int, default=201)
    parser.add_argument("--collector-timeout-seconds", type=int, default=210)
    parser.add_argument("--out-dir", default="artefacts/current_model_validation")
    parser.add_argument("--output-stem", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if not (root / "Dockerfile").exists():
        raise RuntimeError(f"Cannot locate repository root from {__file__}")
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.output_stem or f"headless_ros2_cpp_performance_rate_{str(args.rate).replace('.', 'p')}"

    summary_path = out_dir / f"{stem}_summary.json"
    raw_path = out_dir / f"{stem}_messages.jsonl"
    stats_path = out_dir / f"{stem}_docker_stats.jsonl"
    play_log_path = out_dir / f"{stem}_bag_play.log"
    collector_log_path = out_dir / f"{stem}_collector_stderr.log"
    collector_source = Path(__file__).with_name("headless_ros2_perf_collector.py")

    for path in [summary_path, raw_path, stats_path, play_log_path, collector_log_path]:
        path.unlink(missing_ok=True)

    run(["docker", "exec", args.container, "/bin/bash", "-lc", "pkill -f '/tmp/headless_ros2_perf_collector.py' || true"])
    cp = run(["docker", "cp", str(collector_source), f"{args.container}:/tmp/headless_ros2_perf_collector.py"])
    if cp.returncode != 0:
        raise RuntimeError(f"docker cp failed: {cp.stderr}")

    collector = subprocess.Popen(
        [
            "docker", "exec", args.container, "/ros_entrypoint.sh", "python3",
            "/tmp/headless_ros2_perf_collector.py", args.topic,
            str(args.expected_messages), str(args.collector_timeout_seconds),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(3)

    stop_stats = threading.Event()
    stats_lines = []

    def sample_stats():
        while not stop_stats.is_set():
            sample = run(["docker", "stats", args.container, "--no-stream", "--format", "{{json .}}"])
            if sample.stdout.strip():
                stats_lines.append(sample.stdout.strip())
            time.sleep(1)

    stats_thread = threading.Thread(target=sample_stats, daemon=True)
    stats_thread.start()

    play_command = [
        "docker", "exec", args.container, "/ros_entrypoint.sh", "ros2", "bag", "play",
        "/data", "--rate", str(args.rate), "--read-ahead-queue-size", str(args.read_ahead_queue_size),
    ]
    play_started = time.monotonic()
    play = run(play_command)
    play_finished = time.monotonic()
    stop_stats.set()
    stats_thread.join(timeout=5)

    play_output = (play.stdout or "") + (play.stderr or "")
    play_log_path.write_text(play_output, encoding="utf-8")
    stats_path.write_text("\n".join(stats_lines) + ("\n" if stats_lines else ""), encoding="utf-8")

    try:
        collector_stdout, collector_stderr = collector.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        run(["docker", "exec", args.container, "/bin/bash", "-lc", "pkill -f '/tmp/headless_ros2_perf_collector.py' || true"])
        collector_stdout, collector_stderr = collector.communicate(timeout=10)

    collector_log_path.write_text(collector_stderr or "", encoding="utf-8")
    if not collector_stdout.strip():
        raise RuntimeError(f"collector produced no stdout; stderr saved to {collector_log_path}")

    collected = json.loads(collector_stdout)
    raw_path.write_text(
        "".join(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n" for message in collected["messages"]),
        encoding="utf-8",
    )

    parsed_stats = []
    for line in stats_lines:
        try:
            parsed_stats.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    cpu = [parse_percent(item.get("CPUPerc")) for item in parsed_stats]
    cpu = [value for value in cpu if value is not None]
    mem = [parse_mem_mib(item.get("MemUsage")) for item in parsed_stats]
    mem = [value for value in mem if value is not None]

    summary = collected["summary"]
    summary.update(
        {
            "command": " ".join(play_command),
            "play_exit_code": play.returncode,
            "play_wall_seconds": play_finished - play_started,
            "play_effective_input_hz_assuming_expected_messages": args.expected_messages / (play_finished - play_started),
            "rate": args.rate,
            "read_ahead_queue_size": args.read_ahead_queue_size,
            "docker_stats_sample_count": len(parsed_stats),
            "docker_cpu_percent_max": max(cpu) if cpu else None,
            "docker_cpu_percent_mean": statistics.fmean(cpu) if cpu else None,
            "docker_memory_mib_max": max(mem) if mem else None,
            "docker_memory_mib_mean": statistics.fmean(mem) if mem else None,
            "bag_play_log_contains_starved": "starved" in play_output,
            "bag_play_log_contains_lost": bool(re.search(r"lost|drop|dropped", play_output, re.IGNORECASE)),
            "artifacts": {
                "messages_jsonl": str(raw_path),
                "docker_stats_jsonl": str(stats_path),
                "bag_play_log": str(play_log_path),
                "collector_stderr_log": str(collector_log_path),
            },
        }
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
