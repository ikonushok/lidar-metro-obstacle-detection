"""Bounded lazy reader for one named rosbag2 directory inside a TAR archive."""

from collections import OrderedDict
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2

from cloud_input import inspect_cloud
from stage_2_player import encode_xyz_frame, frame_record


class ArchiveBagFrames:
    """Reads one bag lazily; only its current SQLite part is materialized."""

    def __init__(self, archive_path: Path, bag_prefix: str, dataset_id: str):
        self.archive_path = archive_path
        self.bag_prefix = bag_prefix.rstrip('/')
        self.dataset_id = dataset_id
        self.cache = OrderedDict()
        self.temp = tempfile.TemporaryDirectory(prefix='lidar-cpu-player-')
        self.database = Path(self.temp.name) / 'current.db3'
        self.loaded_part = None
        with tarfile.open(self.archive_path, 'r:') as archive:
            self.members = {member.name.lstrip('./'): member for member in archive if member.isfile()}
            metadata_name = self.bag_prefix + '/metadata.yaml'
            if metadata_name not in self.members:
                raise ValueError('Missing archive metadata: ' + metadata_name)
            self.meta = yaml.safe_load(archive.extractfile(self.members[metadata_name]))['rosbag2_bagfile_information']
        topics = self.meta['topics_with_message_count']
        if len(topics) != 1 or any(item['topic_metadata']['type'] != 'sensor_msgs/msg/PointCloud2' or
                                   item['topic_metadata']['serialization_format'] != 'cdr' for item in topics):
            raise ValueError('Bag must contain exactly one PointCloud2/cdr topic')
        self.topic_name = topics[0]['topic_metadata']['name']
        self.first_ns = int(self.meta['starting_time']['nanoseconds_since_epoch'])
        files = self.meta['files']
        declared_total = sum(int(part['message_count']) for part in files)
        metadata_total = int(self.meta['message_count'])
        # Three supplied single-file bags have a known stale files[].message_count
        # while the top-level count matches SQLite.  Do not silently accept this
        # for multipart archives, where the per-part offsets are essential.
        if declared_total != metadata_total and len(files) != 1:
            raise ValueError('Multipart metadata count mismatch')
        self.lookup, self.part_counts = [], {}
        for part in files:
            member_name = self.bag_prefix + '/' + part['path']
            if member_name not in self.members:
                raise ValueError('Missing archive part: ' + member_name)
            count = metadata_total if len(files) == 1 else int(part['message_count'])
            self.part_counts[member_name] = count
            self.lookup.extend((member_name, offset) for offset in range(count))
        if len(self.lookup) != metadata_total:
            raise ValueError('Metadata count mismatch')

    def release(self):
        """Drop decompressed SQLite and decoded cache when another source becomes active."""
        self.cache.clear()
        self.loaded_part = None
        self.database.unlink(missing_ok=True)

    def close(self):
        self.temp.cleanup()

    def frame(self, index: int):
        if not 0 <= index < len(self.lookup):
            raise IndexError('Frame outside dataset')
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        member_name, offset = self.lookup[index]
        if self.loaded_part != member_name:
            self.release()
            with tarfile.open(self.archive_path, 'r:') as archive:
                with archive.extractfile(self.members[member_name]) as source, self.database.open('wb') as target:
                    shutil.copyfileobj(source, target, 8 * 1024 * 1024)
            self.loaded_part = member_name
        connection = sqlite3.connect(self.database.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            if connection.execute('select count(*) from messages').fetchone()[0] != self.part_counts[member_name]:
                raise ValueError('SQLite count disagrees with metadata')
            row = connection.execute(
                'select m.timestamp,m.data,t.name,t.type,t.serialization_format from messages m '
                'join topics t on t.id=m.topic_id order by m.timestamp,m.id limit 1 offset ?', (offset,)).fetchone()
            if row is None or row[3:] != ('sensor_msgs/msg/PointCloud2', 'cdr'):
                raise ValueError('Invalid PointCloud2 row')
            stamp, data, topic, _message_type, _serialization = row
            stats, xyz = inspect_cloud(deserialize_message(data, PointCloud2))
            record = frame_record(index, stamp, stats, xyz, self.first_ns, '')
            record.update(dataset_id=self.dataset_id, source_part=member_name, source_topic=topic)
            value = record, encode_xyz_frame(xyz)
        finally:
            connection.close()
        self.cache[index] = value
        while len(self.cache) > 3:
            self.cache.popitem(last=False)
        return value
