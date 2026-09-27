"""Actual ros2 bag play -> DDS -> Python input inspection, with count checking."""
import argparse
import json
from pathlib import Path
import resource
import sqlite3
import subprocess
import shutil
import tempfile
import time
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.serialization import deserialize_message
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import PointCloud2
from rosbag2_interfaces.srv import PlayNext, Resume
from cloud_input import inspect_cloud


def main():
    p = argparse.ArgumentParser()
    p.add_argument('bag', type=Path)
    p.add_argument('--topic', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=float, default=120)
    p.add_argument('--raw', action='store_true', help='Receive serialized CDR, then deserialize explicitly')
    p.add_argument('--stage-local', action='store_true', help='Copy bag to container-local temporary storage before replay')
    args = p.parse_args()
    files = list(args.bag.glob('*.db3'))
    if len(files) != 1:
        p.error('Expected exactly one db3')
    db = sqlite3.connect(files[0].resolve().as_uri() + '?mode=ro', uri=True)
    expected = db.execute('select count(*) from messages join topics on messages.topic_id=topics.id where topics.name=?', (args.topic,)).fetchone()[0]
    db.close()
    if not expected:
        p.error('Topic has no messages')
    args.output.mkdir(parents=True, exist_ok=True)
    staging = tempfile.TemporaryDirectory(prefix='lidar-replay-') if args.stage_local else None
    playback_bag = args.bag
    if staging is not None:
        playback_bag = Path(staging.name) / 'bag'
        shutil.copytree(args.bag, playback_bag)
    rclpy.init()
    node = Node('stage_1_input_probe')
    count, errors, durations = 0, [], []
    received_headers = []

    def receive(msg):
        nonlocal count
        begin = time.perf_counter()
        if args.raw:
            msg = deserialize_message(msg, PointCloud2)
        count += 1
        received_headers.append(msg.header.stamp.sec*10**9 + msg.header.stamp.nanosec)
        try:
            inspect_cloud(msg)
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
        durations.append((time.perf_counter()-begin)*1000)

    # Matches offered QoS in both selected bag metadata; no detector contract exists yet.
    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
    subscription = node.create_subscription(PointCloud2, args.topic, receive, qos, raw=args.raw)
    started = time.perf_counter()
    timed_out = False
    with (args.output / 'player.log').open('w') as log:
        player = subprocess.Popen(['ros2', 'bag', 'play', str(playback_bag), '--start-paused', '--wait-for-all-acked', '30000', '--topics', args.topic], stdout=log, stderr=subprocess.STDOUT)
        ended = None
        try:
            next_client = node.create_client(PlayNext, '/rosbag2_player/play_next')
            resume_client = node.create_client(Resume, '/rosbag2_player/resume')
            while not (next_client.service_is_ready() and resume_client.service_is_ready()
                       and node.count_publishers(args.topic)):
                rclpy.spin_once(node, timeout_sec=.1)
                if player.poll() is not None or time.perf_counter()-started > args.timeout:
                    raise RuntimeError('Player did not become ready')
            first = next_client.call_async(PlayNext.Request())
            while not first.done() or count < 1:
                rclpy.spin_once(node, timeout_sec=.1)
                if time.perf_counter()-started > args.timeout:
                    raise RuntimeError('First cloud was not received')
            if not first.result().success:
                raise RuntimeError('Player failed to step first cloud')
            resume = resume_client.call_async(Resume.Request())
            while not resume.done():
                rclpy.spin_once(node, timeout_sec=.1)
                if time.perf_counter()-started > args.timeout:
                    raise RuntimeError('Player did not resume')
            while True:
                rclpy.spin_once(node, timeout_sec=.1)
                now = time.perf_counter()
                if player.poll() is not None:
                    if ended is None:
                        ended = now
                    if now-ended > 3:
                        break
                if now-started > args.timeout:
                    timed_out = True
                    break
        finally:
            if player.poll() is None:
                player.terminate()
                try:
                    player.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    player.kill()
                    player.wait()
            node.destroy_node()
            rclpy.shutdown()
    result = dict(expected=expected, received=count, count_difference=expected-count,
                  unique_header_stamps=len(set(received_headers)), errors=errors,
                  player_exit=player.returncode, timed_out=timed_out,
                  wall_seconds=time.perf_counter()-started,
                  callback_ms_p95=float(np.percentile(durations,95)) if durations else None,
                  peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                  qos='RELIABLE VOLATILE KEEP_LAST depth=10',
                  raw_subscription=args.raw,
                  staged_local=args.stage_local,
                  startup='paused; step and inspect first cloud; resume remaining sequence at rate 1',
                  received_header_ns=received_headers,
                  scope='input only; DDS queue latency not measured; not a real-time claim')
    (args.output / 'replay.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'received_header_ns'}, indent=2))
    if staging is not None:
        staging.cleanup()
    return timed_out or player.returncode != 0 or count != expected or bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
