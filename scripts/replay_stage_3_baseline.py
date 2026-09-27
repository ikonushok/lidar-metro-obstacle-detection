"""Replay a ROS2 bag through the Stage 3 baseline and count result messages."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rosbag2_interfaces.srv import PlayNext, Resume
from std_msgs.msg import String

from stage_3_baseline import baseline_node_class


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag', type=Path)
    parser.add_argument('--input-topic', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--playback-rate', type=float, default=0.25,
                        help='Bag playback rate; slowed replay prevents silently dropping detector results.')
    parser.add_argument('--stage-local', action='store_true')
    args = parser.parse_args()
    if args.playback_rate <= 0:
        parser.error('--playback-rate must be positive')
    databases = list(args.bag.glob('*.db3'))
    if len(databases) != 1:
        parser.error('Expected a directory with exactly one db3 bag database')
    database = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    expected = database.execute(
        'select count(*) from messages join topics on messages.topic_id=topics.id where topics.name=?',
        (args.input_topic,)).fetchone()[0]
    database.close()
    if not expected:
        parser.error('Input topic has no messages')
    args.output.mkdir(parents=True, exist_ok=True)
    staging = tempfile.TemporaryDirectory(prefix='lidar-stage-3-') if args.stage_local else None
    playback_bag = args.bag
    if staging:
        playback_bag = Path(staging.name) / 'bag'
        shutil.copytree(args.bag, playback_bag)
    rclpy.init()
    BaselineNode = baseline_node_class()
    detector = BaselineNode(input_topic=args.input_topic)
    monitor = Node('stage_3_result_monitor')
    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.VOLATILE)
    results, decode_errors = [], []

    def receive(result):
        try:
            results.append(json.loads(result.data))
        except json.JSONDecodeError as exc:
            decode_errors.append(str(exc))

    subscription = monitor.create_subscription(String, '/stage_3/obstacle_candidate', receive, qos)
    del subscription
    player = None
    started = time.perf_counter()
    timed_out = False
    try:
        with (args.output / 'player.log').open('w') as log:
            player = subprocess.Popen(
                ['ros2', 'bag', 'play', str(playback_bag), '--start-paused', '--wait-for-all-acked',
                 '30000', '--rate', str(args.playback_rate), '--topics', args.input_topic],
                stdout=log, stderr=subprocess.STDOUT)
            next_client = monitor.create_client(PlayNext, '/rosbag2_player/play_next')
            resume_client = monitor.create_client(Resume, '/rosbag2_player/resume')
            while not (next_client.service_is_ready() and resume_client.service_is_ready() and
                       detector.count_publishers(args.input_topic)):
                rclpy.spin_once(detector, timeout_sec=.05)
                rclpy.spin_once(monitor, timeout_sec=.05)
                if player.poll() is not None or time.perf_counter() - started > args.timeout:
                    raise RuntimeError('Player did not become ready')
            first = next_client.call_async(PlayNext.Request())
            while not first.done() or not results:
                rclpy.spin_once(detector, timeout_sec=.05)
                rclpy.spin_once(monitor, timeout_sec=.05)
                if time.perf_counter() - started > args.timeout:
                    raise RuntimeError('First result was not received')
            if not first.result().success:
                raise RuntimeError('Player failed to step first cloud')
            resume = resume_client.call_async(Resume.Request())
            while not resume.done():
                rclpy.spin_once(detector, timeout_sec=.05)
                rclpy.spin_once(monitor, timeout_sec=.05)
                if time.perf_counter() - started > args.timeout:
                    raise RuntimeError('Player did not resume')
            player_ended = None
            while True:
                rclpy.spin_once(detector, timeout_sec=.05)
                rclpy.spin_once(monitor, timeout_sec=.05)
                now = time.perf_counter()
                if player.poll() is not None:
                    player_ended = player_ended or now
                    if now - player_ended > 3:
                        break
                if now - started > args.timeout:
                    timed_out = True
                    break
    finally:
        if player and player.poll() is None:
            player.terminate()
            try:
                player.wait(timeout=5)
            except subprocess.TimeoutExpired:
                player.kill()
                player.wait()
        monitor.destroy_node()
        detector.destroy_node()
        rclpy.shutdown()
        if staging:
            staging.cleanup()
    summary = {
        'expected_input_messages': expected,
        'received_results': len(results),
        'count_difference': expected - len(results),
        'result_status_counts': {status: sum(r['status'] == status for r in results)
                                 for status in sorted({r['status'] for r in results})},
        'decode_errors': decode_errors,
        'player_exit': player.returncode if player else None,
        'timed_out': timed_out,
        'playback_rate': args.playback_rate,
        'wall_seconds': time.perf_counter() - started,
        'scope': 'ASSUMED_HACKATHON lidar_livox candidate-only baseline; not a safety or quality claim',
    }
    success = not (timed_out or player.returncode != 0 or len(results) != expected or bool(decode_errors))
    (args.output / 'stage_3_replay.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    result_path = args.output / ('stage_3_results.jsonl' if success else 'stage_3_results.failed.jsonl')
    with result_path.open('w', encoding='utf-8') as stream:
        for result in results:
            stream.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(json.dumps(summary, indent=2))
    return not success


if __name__ == '__main__':
    raise SystemExit(main())
