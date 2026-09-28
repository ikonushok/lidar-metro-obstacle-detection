import argparse
import json
import re
import statistics
import subprocess
import threading
import time
import uuid
from pathlib import Path


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, **kwargs)


def start_container_process(container, command, **kwargs):
    pid_path = f"/tmp/headless_perf_{uuid.uuid4().hex}.pid"
    process = subprocess.Popen(
        ["docker", "exec", container, "/ros_entrypoint.sh", "bash", "-c",
         'echo $$ > "$1"; shift; exec "$@"', "bash", pid_path, *command],
        text=True, **kwargs,
    )
    return process, pid_path


def finish_container_process(container, process, pid_path):
    # Terminating docker exec on the host does not stop its container process.
    # Signal only the PID owned by this measurement, never another collector.
    code = (
        "import os,pathlib,signal,sys; p=pathlib.Path(sys.argv[1]); "
        "pid=int(p.read_text()) if p.exists() else None; "
        "p.unlink(missing_ok=True); "
        "os.kill(pid,signal.SIGTERM) if pid and sys.argv[2]=='stop' else None"
    )
    return run(["docker", "exec", container, "python3", "-c", code, pid_path,
                "stop" if process.poll() is None else "cleanup"], timeout=10)


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
    if (args.expected_messages <= 0 or args.collector_timeout_seconds <= 0
            or args.rate <= 0 or args.read_ahead_queue_size <= 0):
        parser.error("message count, timeout, rate and queue size must be positive")

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

    cp = run(["docker", "cp", str(collector_source), f"{args.container}:/tmp/headless_ros2_perf_collector.py"])
    if cp.returncode != 0:
        raise RuntimeError(f"docker cp failed: {cp.stderr}")

    collector_started = time.monotonic()
    collector, collector_pid = start_container_process(
        args.container,
        [
            "python3",
            "/tmp/headless_ros2_perf_collector.py", args.topic,
            str(args.expected_messages), str(args.collector_timeout_seconds),
        ],
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
        "--start-paused", "--disable-keyboard-controls",
        "--wait-for-all-acked", "5000",
    ]
    play_started = time.monotonic()
    play_error = None
    service_outputs = []
    with play_log_path.open("w", encoding="utf-8") as play_log:
        play, play_pid = start_container_process(
            args.container, play_command[4:], stdout=play_log, stderr=subprocess.STDOUT,
        )
        try:
            # play_next waits for the initial queue while the player clock is
            # paused; resuming afterwards avoids an overdue startup burst.
            for service, service_type in [("play_next", "PlayNext"), ("resume", "Resume")]:
                remaining = args.collector_timeout_seconds - (time.monotonic() - collector_started)
                response = run(
                    ["docker", "exec", args.container, "/ros_entrypoint.sh", "ros2", "service", "call",
                     f"/rosbag2_player/{service}", f"rosbag2_interfaces/srv/{service_type}", "{}"],
                    timeout=max(1, remaining),
                )
                service_outputs.append(response.stdout + response.stderr)
                # Humble Resume has an empty response; only PlayNext returns success.
                if response.returncode != 0 or (service == "play_next" and "success=True" not in response.stdout):
                    raise RuntimeError(f"{service} failed: {response.stdout} {response.stderr}")
            remaining = args.collector_timeout_seconds - (time.monotonic() - collector_started)
            play.wait(timeout=max(1, remaining))
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            play_error = str(exc)
        finally:
            finish_container_process(args.container, play, play_pid)
            play.wait(timeout=10)
            play_finished = time.monotonic()
            stop_stats.set()
            stats_thread.join(timeout=5)

    play_output = play_log_path.read_text(encoding="utf-8")
    stats_path.write_text("\n".join(stats_lines) + ("\n" if stats_lines else ""), encoding="utf-8")

    try:
        remaining = args.collector_timeout_seconds - (time.monotonic() - collector_started)
        collector_stdout, collector_stderr = collector.communicate(timeout=max(1, remaining) + 10)
    except subprocess.TimeoutExpired:
        finish_container_process(args.container, collector, collector_pid)
        collector_stdout, collector_stderr = collector.communicate(timeout=10)
    finally:
        finish_container_process(args.container, collector, collector_pid)

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
            "collector_exit_code": collector.returncode,
            "play_error": play_error,
            "startup_service_output": service_outputs,
            "play_wall_includes_startup_pause": True,
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
    if (play_error or play.returncode != 0 or collector.returncode != 0
            or summary["received_messages"] != args.expected_messages):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
