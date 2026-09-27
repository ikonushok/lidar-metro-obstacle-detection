"""Format helpers for the visual-only Stage 2 LiDAR browser player."""

import json
import math
from pathlib import Path

import numpy as np


PLAYER_FORMAT_VERSION = 1
XYZ_FLOAT32_BYTES = 12
VISUAL_REFERENCE_CROP_MARGIN_M = 0.5
VISUAL_REFERENCE_CROP_SIDES = ('left', 'right', 'top', 'bottom')


def load_stage_3_results(path, records):
    """Attach recorded non-safety Stage 3 bounds to matching player frames."""
    if path is None:
        return False
    lines = [line for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(lines) != len(records):
        raise ValueError('Stage 3 result count does not match player frames')
    allowed_statuses = {
        'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY',
        'WARNING_CANDIDATE_ASSUMED_GEOMETRY',
        'UNKNOWN',
    }
    for record, line in zip(records, lines):
        result = json.loads(line)
        if (result.get('status') not in allowed_statuses or
                result.get('safety_decision_permitted') or result.get('clear_decision_permitted') or
                str(result.get('header_timestamp_ns')) != record['header_timestamp_ns'] or
                result.get('source_frame') != record['source_frame']):
            raise ValueError('Stage 3 result does not match the non-safety player contract')
        record['stage_3_baseline'] = {
            'status': result['status'],
            'reason': result.get('reason'),
            'geometry_basis': result.get('geometry_basis'),
            'approximate_nearest_distance_m': result.get('approximate_nearest_distance_m'),
            'approximate_distance_label': result.get('approximate_distance_label'),
            'clusters': result.get('clusters', []),
            'protrusion_clusters': result.get('protrusion_clusters', []),
            'path_profile': result.get('path_profile', {'status': 'NOT_REPORTED'}),
            'path_profiles': result.get('path_profiles', {}),
        }
    return True


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


def visual_reference_crop(visual_contract, margin_m=VISUAL_REFERENCE_CROP_MARGIN_M):
    """Describe a display-only crop in the unconfirmed source coordinates.

    The caller must not use this as a train clearance or a safety envelope.
    This player only supports the explicitly documented visual hypothesis.
    """
    assumption = visual_contract['source_axis_assumption']
    expected_axes = {
        'longitudinal_axis': 'y', 'longitudinal_sign': -1,
        'lateral_axis': 'x', 'vertical_axis': 'z', 'source_units': 'm',
    }
    if any(assumption.get(key) != value for key, value in expected_axes.items()):
        raise ValueError('Visual reference crop requires the -Y/X/Z metre hypothesis')
    if margin_m <= 0:
        raise ValueError('Visual reference crop margin must be positive')
    placement = visual_contract['placement_in_source_coordinates']
    reference = visual_contract['reference_cross_section']
    x = reference['lateral_extent_m']
    z = reference['vertical_extent_above_rail_m']
    return {
        'status': 'UNCONFIRMED',
        'label': 'UNCONFIRMED visual filter: reference clearance + %.1f m' % margin_m,
        'purpose': 'MANUAL_VISUAL_REVIEW_ONLY',
        'safety_decision_permitted': False,
        'margins_m': {side: margin_m for side in VISUAL_REFERENCE_CROP_SIDES},
        'longitudinal_filter': 'NONE',
        'bounds_source_coordinates': {
            # The browser applies the adjustable margin to these base bounds.
            'x': {'min': placement['track_centerline_lateral_m'] + x['min'],
                  'max': placement['track_centerline_lateral_m'] + x['max']},
            'z': {'min': placement['rail_head_vertical_m'] + z['min'],
                  'max': placement['rail_head_vertical_m'] + z['max']},
        },
    }


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
