"""Format helpers for the LiDAR browser player."""

import math

import numpy as np


XYZ_FLOAT32_BYTES = 12


def encode_xyz_frame(xyz):
    """Return every usable XYZ return as little-endian float32 triples.

    ``cloud_input.inspect_cloud`` supplies finite, non-zero XYZ returns.  This
    function deliberately does not sample, voxelise, crop, or reorder them.
    """
    points = np.asarray(xyz)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError('XYZ must have shape (N, 3)')
    if not np.isfinite(points).all():
        raise ValueError('XYZ contains non-finite values')
    return np.ascontiguousarray(points, dtype='<f4').tobytes()


def closest_return_distance_m(xyz):
    """Euclidean sensor-origin distance for display, not obstacle distance."""
    points = np.asarray(xyz)
    if not len(points):
        return None
    squared = np.einsum('ij,ij->i', points, points)
    return math.sqrt(float(squared.min()))


def frame_record(frame_index, bag_ns, stats, xyz, first_bag_ns, filename):
    """Build browser metadata without deriving a geometric/safety result."""
    if bag_ns < first_bag_ns:
        raise ValueError('bag time precedes the first frame')
    return {
        'index': frame_index,
        'file': filename,
        'bag_offset_seconds': (bag_ns - first_bag_ns) / 1_000_000_000.0,
        'bag_timestamp_ns': bag_ns,
        # JavaScript numbers cannot represent nanosecond epoch timestamps exactly.
        'header_timestamp_ns': str(stats['header_ns']),
        'source_frame': stats['frame'],
        'source_points': stats['points'],
        'finite_points': stats['finite'],
        'zero_xyz_returns': stats['zero'],
        'nonfinite_points': stats['nonfinite'],
        'displayed_points': len(xyz),
        'closest_return_distance_m': closest_return_distance_m(xyz),
    }
