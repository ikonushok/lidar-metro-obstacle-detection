"""Read-only recurrence audit for recorded Stage 3 candidate bounds."""

import math


def full_cloud_clusters(xyz, voxel_size_m, min_points, forward_max_m):
    """Visual recurrence input independent of the detection envelope."""
    import numpy as np
    from stage_3_baseline import voxel_components
    points = xyz[(np.isfinite(xyz).all(axis=1)) &
                 (-xyz[:, 1] >= 0) & (-xyz[:, 1] <= forward_max_m)]
    output = []
    for indices in voxel_components(points, voxel_size_m):
        if len(indices) < min_points:
            continue
        component = points[indices]
        output.append({'zone': 'VISUAL_FULL_CLOUD', 'points': len(indices),
                       'bounds_source_coordinates': {
                           axis: {'min': float(component[:, i].min()),
                                  'max': float(component[:, i].max())}
                           for i, axis in enumerate(('x', 'y', 'z'))}})
    return output


def _bounds_center(bounds):
    return tuple((float(bounds[axis]['min']) + float(bounds[axis]['max'])) / 2.0
                 for axis in ('x', 'y', 'z'))


def _key(center, voxel_size_m):
    return tuple(math.floor(value / voxel_size_m) for value in center)


def audit_source_coordinate_recurrence(results, frames, first_frame, last_frame,
                                       voxel_size_m=0.5, min_frame_fraction=0.8):
    """Group repeated source-coordinate cluster centres without claiming tracking.

    A sensor frame can move between messages. Therefore recurrence in this
    function is only a diagnostic of repeated source-coordinate bins, never an
    identity association, static-map result, or physical persistence claim.
    """
    if len(results) != len(frames):
        raise ValueError('results and manifest frames must have equal length')
    if first_frame < 0 or last_frame < first_frame or last_frame >= len(frames):
        raise ValueError('frame window is outside the manifest')
    if not math.isfinite(voxel_size_m) or voxel_size_m <= 0:
        raise ValueError('voxel_size_m must be positive')
    if not 0 < min_frame_fraction <= 1:
        raise ValueError('min_frame_fraction must be in (0, 1]')

    selected_results = results[first_frame:last_frame + 1]
    selected_frames = frames[first_frame:last_frame + 1]
    groups = {}
    for frame_index, (result, frame) in enumerate(zip(selected_results, selected_frames), first_frame):
        if (str(result.get('header_timestamp_ns')) != str(frame['header_timestamp_ns']) or
                result.get('source_frame') != frame['source_frame']):
            raise ValueError('results do not match manifest frames')
        for cluster in result.get('clusters', []):
            bounds = cluster.get('bounds_source_coordinates')
            if not bounds:
                continue
            center = _bounds_center(bounds)
            key = _key(center, voxel_size_m)
            group = groups.setdefault(key, {
                'source_coordinate_voxel': list(key),
                'frame_indices': set(),
                'zone_counts': {},
                'bounds_source_coordinates': {
                    axis: {'min': float('inf'), 'max': float('-inf')} for axis in ('x', 'y', 'z')
                },
            })
            group['frame_indices'].add(frame_index)
            zone = cluster.get('zone', 'UNKNOWN_ZONE')
            group['zone_counts'][zone] = group['zone_counts'].get(zone, 0) + 1
            for axis in ('x', 'y', 'z'):
                group['bounds_source_coordinates'][axis]['min'] = min(
                    group['bounds_source_coordinates'][axis]['min'], float(bounds[axis]['min']))
                group['bounds_source_coordinates'][axis]['max'] = max(
                    group['bounds_source_coordinates'][axis]['max'], float(bounds[axis]['max']))

    frame_count = len(selected_results)
    min_frames = math.ceil(frame_count * min_frame_fraction)
    output = []
    for group in groups.values():
        frames_present = sorted(group.pop('frame_indices'))
        appearances = len(frames_present)
        output.append({
            **group,
            'frames_present': frames_present,
            'frames_with_bin': appearances,
            'recurrence_fraction': appearances / frame_count,
            'is_recurrent': appearances >= min_frames,
        })
    output.sort(key=lambda group: (-group['frames_with_bin'], group['source_coordinate_voxel']))
    return {
        'frame_window_inclusive': [first_frame, last_frame],
        'frames': frame_count,
        'source_coordinate_voxel_size_m': voxel_size_m,
        'minimum_recurrence_fraction': min_frame_fraction,
        'minimum_frames': min_frames,
        'groups': output,
        'recurrent_groups': [group for group in output if group['is_recurrent']],
        'scope': ('DEVELOPMENT_DIAGNOSTIC_ONLY: recurrence of unaligned source-coordinate bins; '
                  'not tracking, static map, physical persistence, or a safety decision'),
    }
