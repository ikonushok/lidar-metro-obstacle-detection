"""Candidate-only envelope baseline for the explicitly assumed hackathon geometry.

This module deliberately emits no CLEAR/NO_OBSTACLE decision.  It is a demo
implementation with explicit development profiles; production geometry must replace the
``ASSUMED_HACKATHON`` contract before activation.
"""
import argparse
import json
from collections import deque
from pathlib import Path
import time

import numpy as np
import yaml

from cloud_input import inspect_cloud


ASSUMED_STATUS = 'ASSUMED_HACKATHON'
UNKNOWN = 'UNKNOWN'


def load_geometry_contract(path):
    with Path(path).open(encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def contract_issues(config, source_frame):
    activation = config.get('activation', {})
    frames = config.get('frames', {})
    envelope = config.get('universal_fleet_envelope', {})
    path = config.get('path', {})
    safety = config.get('safety_envelope', {})
    warning = config.get('warning_layer', {})
    detection = config.get('detection', {})
    auto_grade = config.get('auto_grade_path', {})
    auto_track = config.get('auto_track_path', {})
    if not activation.get('obstacle_candidate_enabled'):
        return ['OBSTACLE_CANDIDATE_DISABLED']
    if activation.get('geometric_decision_enabled'):
        return ['SAFETY_DECISION_MUST_REMAIN_DISABLED']
    if activation.get('safety_decision_permitted') or activation.get('clear_decision_permitted'):
        return ['SAFETY_OR_CLEAR_DECISION_MUST_REMAIN_DISABLED']
    for name, value in (
        ('contract', config.get('contract', {}).get('status')),
        ('frames', frames.get('status')),
        ('envelope', envelope.get('status')),
        ('path', path.get('status')),
        ('safety_envelope', safety.get('status')),
        ('warning_layer', warning.get('status')),
        ('detection', detection.get('status')),
    ):
        if value != ASSUMED_STATUS:
            return ['%s_STATUS_NOT_ASSUMED_HACKATHON' % name.upper()]
    if frames.get('source_frame_policy', {}).get(source_frame) != 'ASSUMED_HACKATHON_ACTIVE':
        return ['SOURCE_FRAME_NOT_ACTIVE_FOR_HACKATHON_DEMO']
    if frames.get('geometry_mode') == 'SOURCE_FRAME_IDENTITY_EXPERIMENT':
        # This is an explicit source-coordinate hypothesis, never a calibration
        # or a transform implementation. No XYZ or header frame is changed.
        extrinsics = frames.get('lidar_mounting_extrinsics', {})
        if (source_frame != 'hesai_lidar' or frames.get('working_frame') != source_frame or
                frames.get('target_from_source') != f'{source_frame} <- {source_frame}' or
                extrinsics.get('source_frame') != source_frame or
                extrinsics.get('target_frame') != source_frame or
                extrinsics.get('transform') != {
                    'translation_m': [0.0, 0.0, 0.0], 'rotation_xyzw': [0.0, 0.0, 0.0, 1.0]}):
            return ['INVALID_SOURCE_FRAME_IDENTITY_EXPERIMENT']
        if (frames.get('axis_directions') != {
                'x': 'LATERAL_RIGHT_FACING_FORWARD_ASSUMED',
                'y': 'LONGITUDINAL_FORWARD_IS_NEGATIVE_Y_ASSUMED',
                'z': 'VERTICAL_UP_ASSUMED'} or
                envelope.get('polygon_in_working_frame', {}).get('coordinate_system') != source_frame or
                path.get('rail_centerline_in_working_frame', {}).get('forward_axis') != '-y'):
            return ['UNSUPPORTED_EXPERIMENT_AXIS_CONTRACT']
    elif (frames.get('geometry_mode') is not None or
          frames.get('target_from_source') != 'hackathon_track_lidar_livox <- lidar_livox'):
        return ['UNEXPECTED_DEMO_TRANSFORM_CONTRACT']
    if frames.get('units') != 'm' or frames.get('units_status') != ASSUMED_STATUS:
        return ['UNEXPECTED_DEMO_UNIT_CONTRACT']
    if not (detection.get('roi', {}).get('forward_min_m', 0) >= 0 and
            detection.get('roi', {}).get('forward_max_m', 0) > 0 and
            detection.get('clustering', {}).get('voxel_size_m', 0) > 0 and
            detection.get('clustering', {}).get('min_cluster_points', 0) > 0):
        return ['INVALID_ASSUMED_DETECTION_PARAMETERS']
    offsets = warning.get('offsets_from_profile_m', {})
    if any(float(offsets.get(side, -1)) < 0 for side in ('left', 'right', 'top', 'bottom')):
        return ['INVALID_ASSUMED_WARNING_LAYER']
    if auto_grade.get('enabled'):
        estimation = auto_grade.get('estimation', {})
        if (auto_grade.get('status') != ASSUMED_STATUS or
                auto_grade.get('safety_decision_permitted') or
                len(estimation.get('lateral_window_m', [])) != 2 or
                len(estimation.get('fit_forward_range_m', [])) != 2 or
                float(estimation.get('bin_size_m', 0)) <= 0 or
                estimation.get('support_surface') != 'FLOOR_UNDER_RAILS_ASSUMED' or
                not 0 < float(estimation.get('floor_support_quantile_z', -1)) < 1 or
                int(estimation.get('min_points_per_bin', 0)) <= 0 or
                int(estimation.get('min_valid_bins', 0)) < 2 or
                float(estimation.get('max_abs_grade', 0)) <= 0 or
                float(estimation.get('max_fit_residual_m', 0)) <= 0):
            return ['INVALID_ASSUMED_AUTO_GRADE_PARAMETERS']
    if auto_track.get('enabled'):
        estimation = auto_track.get('estimation', {})
        if (auto_track.get('status') != ASSUMED_STATUS or
                auto_track.get('safety_decision_permitted') or
                len(estimation.get('fit_forward_range_m', [])) != 2 or
                float(estimation.get('bin_size_m', 0)) <= 0 or
                estimation.get('support_surface') != 'FLOOR_UNDER_RAILS_ASSUMED' or
                float(estimation.get('lateral_search_half_width_m', 0)) <= 0 or
                not 0 < float(estimation.get('floor_support_quantile_z', -1)) < 1 or
                float(estimation.get('floor_band_above_quantile_m', 0)) <= 0 or
                int(estimation.get('min_points_per_bin', 0)) <= 0 or
                int(estimation.get('min_valid_bins', 0)) < 2 or
                float(estimation.get('max_lateral_step_m', 0)) <= 0 or
                float(estimation.get('max_abs_grade', 0)) <= 0):
            return ['INVALID_ASSUMED_AUTO_TRACK_PARAMETERS']
    return []


def assumed_envelope_masks(xyz, config):
    """Return core and warning masks plus forward depth for the demo geometry."""
    profile = config['universal_fleet_envelope']['polygon_in_working_frame']
    path = config['path']['rail_centerline_in_working_frame']
    roi = config['detection']['roi']
    margin = float(config['safety_envelope']['margin'])
    tolerance = float(config['detection']['numeric_boundary_tolerance_m'])
    warning = config['warning_layer']['offsets_from_profile_m']
    lateral_min, lateral_max = map(float, profile['lateral_extent_m'])
    vertical_min, vertical_max = map(float, profile['vertical_extent_m'])
    depth = -xyz[:, 1]
    in_roi = (
        (depth >= float(roi['forward_min_m']) - tolerance) &
        (depth <= float(roi['forward_max_m']) + tolerance) &
        (xyz[:, 0] >= float(path['x_m']) + lateral_min - float(warning['left']) - tolerance) &
        (xyz[:, 0] <= float(path['x_m']) + lateral_max + float(warning['right']) + tolerance) &
        (xyz[:, 2] >= float(path['z_m']) + vertical_min - float(warning['bottom']) - tolerance) &
        (xyz[:, 2] <= float(path['z_m']) + vertical_max + float(warning['top']) + tolerance)
    )
    in_core = (
        in_roi &
        (xyz[:, 0] >= float(path['x_m']) + lateral_min - margin - tolerance) &
        (xyz[:, 0] <= float(path['x_m']) + lateral_max + margin + tolerance) &
        (xyz[:, 2] >= float(path['z_m']) + vertical_min - margin - tolerance) &
        (xyz[:, 2] <= float(path['z_m']) + vertical_max + margin + tolerance)
    )
    return in_core, in_roi, depth


def estimate_auto_grade_path(xyz, config):
    """Estimate a per-frame vertical path hypothesis from dense near-field support.

    The estimate is deliberately candidate-only.  It is never a map update or
    a reason to remove straight-envelope candidates.
    """
    auto = config.get('auto_grade_path', {})
    if not auto.get('enabled'):
        return {'status': 'DISABLED'}
    estimation = auto['estimation']
    lateral_min, lateral_max = map(float, estimation['lateral_window_m'])
    start, end = map(float, estimation['fit_forward_range_m'])
    bin_size = float(estimation['bin_size_m'])
    depth = -xyz[:, 1]
    support = ((xyz[:, 0] >= lateral_min) & (xyz[:, 0] <= lateral_max) &
               (depth >= start) & (depth <= end))
    samples = []
    for lower in np.arange(start, end, bin_size):
        upper = min(lower + bin_size, end)
        points = xyz[support & (depth >= lower) & (depth < upper)]
        if len(points) < int(estimation['min_points_per_bin']):
            continue
        samples.append(((lower + upper) / 2.0,
                        float(np.quantile(points[:, 2], float(estimation['floor_support_quantile_z'])))))
    if len(samples) < int(estimation['min_valid_bins']):
        return {'status': 'UNKNOWN_INSUFFICIENT_SUPPORT', 'valid_bins': len(samples)}
    sample_depths, sample_z = np.asarray(samples, dtype=np.float64).T
    grade, intercept = np.polyfit(sample_depths, sample_z, 1)
    residual = float(np.max(np.abs(sample_z - (grade * sample_depths + intercept))))
    if abs(grade) > float(estimation['max_abs_grade']):
        return {'status': 'UNKNOWN_GRADE_OUT_OF_RANGE', 'valid_bins': len(samples),
                'grade_m_per_m': float(grade), 'max_fit_residual_m': residual}
    if residual > float(estimation['max_fit_residual_m']):
        return {'status': 'UNKNOWN_FIT_RESIDUAL_TOO_HIGH', 'valid_bins': len(samples),
                'grade_m_per_m': float(grade), 'max_fit_residual_m': residual}
    return {'status': 'ACTIVE_ASSUMED_AUTO_GRADE', 'valid_bins': len(samples),
            'z_intercept_m': float(intercept), 'grade_m_per_m': float(grade),
            'max_fit_residual_m': residual,
            'fit_forward_range_m': [start, end]}


def estimate_auto_track_path(xyz, config):
    """Build a local candidate-only 3D track polyline from floor support.

    This is an assumed floor/rail-support hypothesis, not rail recognition.  A
    missing or discontinuous support never removes the straight baseline.
    """
    auto = config.get('auto_track_path', {})
    if not auto.get('enabled'):
        return {'status': 'DISABLED'}
    estimation = auto['estimation']
    start, end = map(float, estimation['fit_forward_range_m'])
    bin_size = float(estimation['bin_size_m'])
    search_half_width = float(estimation['lateral_search_half_width_m'])
    floor_quantile = float(estimation['floor_support_quantile_z'])
    floor_band = float(estimation['floor_band_above_quantile_m'])
    max_step = float(estimation['max_lateral_step_m'])
    max_grade = float(estimation['max_abs_grade'])
    depth = -xyz[:, 1]
    center_x = float(estimation['initial_lateral_center_m'])
    nodes = []
    rejected_bins = 0
    for lower in np.arange(start, end, bin_size):
        upper = min(lower + bin_size, end)
        in_gate = ((depth >= lower) & (depth < upper) &
                   (xyz[:, 0] >= center_x - search_half_width) &
                   (xyz[:, 0] <= center_x + search_half_width))
        points = xyz[in_gate]
        if len(points) < int(estimation['min_points_per_bin']):
            rejected_bins += 1
            continue
        floor_z = float(np.quantile(points[:, 2], floor_quantile))
        floor_points = points[points[:, 2] <= floor_z + floor_band]
        if len(floor_points) < int(estimation['min_points_per_bin']):
            rejected_bins += 1
            continue
        proposed_x = float(np.median(floor_points[:, 0]))
        if nodes and abs(proposed_x - center_x) > max_step:
            rejected_bins += 1
            continue
        proposed_depth = (lower + upper) / 2.0
        if nodes:
            previous = nodes[-1]
            horizontal = float(np.hypot(proposed_x - previous['x_m'],
                                        proposed_depth - previous['depth_m']))
            grade = abs((floor_z - previous['z_m']) / max(horizontal, 1e-9))
            if grade > max_grade:
                rejected_bins += 1
                continue
        center_x = proposed_x
        nodes.append({'depth_m': float(proposed_depth), 'x_m': center_x,
                      'y_m': -float(proposed_depth), 'z_m': floor_z})
    if len(nodes) < int(estimation['min_valid_bins']):
        return {'status': 'UNKNOWN_INSUFFICIENT_TRACK_SUPPORT',
                'valid_bins': len(nodes), 'rejected_bins': rejected_bins}
    return {'status': 'ACTIVE_ASSUMED_AUTO_TRACK', 'valid_bins': len(nodes),
            'rejected_bins': rejected_bins, 'nodes': nodes,
            'fit_forward_range_m': [start, end],
            'support_surface': estimation['support_surface']}


def _envelope_masks_at_vertical_reference(xyz, depth, config, vertical_reference):
    profile = config['universal_fleet_envelope']['polygon_in_working_frame']
    path = config['path']['rail_centerline_in_working_frame']
    roi = config['detection']['roi']
    margin = float(config['safety_envelope']['margin'])
    tolerance = float(config['detection']['numeric_boundary_tolerance_m'])
    warning = config['warning_layer']['offsets_from_profile_m']
    lateral_min, lateral_max = map(float, profile['lateral_extent_m'])
    vertical_min, vertical_max = map(float, profile['vertical_extent_m'])
    in_warning = (
        (depth >= float(roi['forward_min_m']) - tolerance) &
        (depth <= float(roi['forward_max_m']) + tolerance) &
        (xyz[:, 0] >= float(path['x_m']) + lateral_min - float(warning['left']) - tolerance) &
        (xyz[:, 0] <= float(path['x_m']) + lateral_max + float(warning['right']) + tolerance) &
        (xyz[:, 2] >= vertical_reference + vertical_min - float(warning['bottom']) - tolerance) &
        (xyz[:, 2] <= vertical_reference + vertical_max + float(warning['top']) + tolerance)
    )
    in_core = (
        in_warning &
        (xyz[:, 0] >= float(path['x_m']) + lateral_min - margin - tolerance) &
        (xyz[:, 0] <= float(path['x_m']) + lateral_max + margin + tolerance) &
        (xyz[:, 2] >= vertical_reference + vertical_min - margin - tolerance) &
        (xyz[:, 2] <= vertical_reference + vertical_max + margin + tolerance)
    )
    return in_core, in_warning


def _envelope_masks_along_track_polyline(xyz, config, nodes):
    """Intersect points with a sweep of the assumed profile along 3D nodes."""
    profile = config['universal_fleet_envelope']['polygon_in_working_frame']
    roi = config['detection']['roi']
    margin = float(config['safety_envelope']['margin'])
    tolerance = float(config['detection']['numeric_boundary_tolerance_m'])
    warning = config['warning_layer']['offsets_from_profile_m']
    lateral_min, lateral_max = map(float, profile['lateral_extent_m'])
    vertical_min, vertical_max = map(float, profile['vertical_extent_m'])
    core = np.zeros(len(xyz), dtype=bool)
    warning_mask = np.zeros(len(xyz), dtype=bool)
    xy = xyz[:, :2]
    for start, end in zip(nodes, nodes[1:]):
        origin = np.array([start['x_m'], start['y_m']], dtype=np.float64)
        endpoint = np.array([end['x_m'], end['y_m']], dtype=np.float64)
        vector = endpoint - origin
        length = float(np.linalg.norm(vector))
        if length <= tolerance:
            continue
        delta = xy - origin
        fraction = (delta @ vector) / (length * length)
        on_segment = (fraction >= -tolerance) & (fraction <= 1.0 + tolerance)
        lateral = (vector[0] * delta[:, 1] - vector[1] * delta[:, 0]) / length
        vertical_reference = start['z_m'] + fraction * (end['z_m'] - start['z_m'])
        local_warning = (
            on_segment &
            (lateral >= lateral_min - float(warning['left']) - tolerance) &
            (lateral <= lateral_max + float(warning['right']) + tolerance) &
            (xyz[:, 2] >= vertical_reference + vertical_min - float(warning['bottom']) - tolerance) &
            (xyz[:, 2] <= vertical_reference + vertical_max + float(warning['top']) + tolerance)
        )
        local_core = (
            local_warning &
            (lateral >= lateral_min - margin - tolerance) &
            (lateral <= lateral_max + margin + tolerance) &
            (xyz[:, 2] >= vertical_reference + vertical_min - margin - tolerance) &
            (xyz[:, 2] <= vertical_reference + vertical_max + margin + tolerance)
        )
        warning_mask |= local_warning
        core |= local_core
    return core, warning_mask


def candidate_envelope_masks(xyz, config):
    """Return the conservative union of straight, grade, and local-track paths."""
    straight_core, straight_warning, depth = assumed_envelope_masks(xyz, config)
    auto_grade = estimate_auto_grade_path(xyz, config)
    auto_grade_core = np.zeros(len(xyz), dtype=bool)
    auto_grade_warning = np.zeros(len(xyz), dtype=bool)
    if auto_grade['status'] == 'ACTIVE_ASSUMED_AUTO_GRADE':
        reference = auto_grade['z_intercept_m'] + auto_grade['grade_m_per_m'] * depth
        auto_grade_core, auto_grade_warning = _envelope_masks_at_vertical_reference(
            xyz, depth, config, reference)
    auto_track = estimate_auto_track_path(xyz, config)
    auto_track_core = np.zeros(len(xyz), dtype=bool)
    auto_track_warning = np.zeros(len(xyz), dtype=bool)
    if auto_track['status'] == 'ACTIVE_ASSUMED_AUTO_TRACK':
        auto_track_core, auto_track_warning = _envelope_masks_along_track_polyline(
            xyz, config, auto_track['nodes'])
    profiles = {'auto_grade': auto_grade, 'auto_track': auto_track}
    selected = auto_track if auto_track['status'] == 'ACTIVE_ASSUMED_AUTO_TRACK' else auto_grade
    return (straight_core | auto_grade_core | auto_track_core,
            straight_warning | auto_grade_warning | auto_track_warning,
            depth, selected, profiles, straight_warning, auto_grade_warning,
            auto_grade_core, auto_track_warning, auto_track_core)


def points_in_assumed_envelope(xyz, config):
    """Return all core-or-warning points and forward depth for compatibility."""
    _, in_warning, depth, *_ = candidate_envelope_masks(xyz, config)
    return xyz[in_warning], depth[in_warning]


def voxel_components(points, voxel_size_m):
    """Connect occupied 26-neighbour voxels and retain all original points."""
    if not len(points):
        return []
    voxels = np.floor(points / voxel_size_m).astype(np.int64)
    by_voxel = {}
    for index, cell in enumerate(voxels):
        by_voxel.setdefault(tuple(cell), []).append(index)
    remaining = set(by_voxel)
    components = []
    offsets = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)]
    while remaining:
        first = remaining.pop()
        queue = deque([first])
        indices = []
        while queue:
            cell = queue.popleft()
            indices.extend(by_voxel[cell])
            for dx, dy, dz in offsets:
                neighbour = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
        components.append(np.asarray(indices, dtype=np.int64))
    return components


def protrusion_clusters(xyz, config, profiles):
    """Additional above-floor components; never suppress baseline returns."""
    settings = config['detection'].get('protrusion_segmentation', {})
    if not settings.get('enabled'):
        return []
    depth = -xyz[:, 1]
    floor = np.full(len(xyz), np.nan)
    grade = profiles.get('auto_grade', {})
    if grade.get('status') == 'ACTIVE_ASSUMED_AUTO_GRADE':
        floor[:] = grade['z_intercept_m'] + depth * grade['grade_m_per_m']
    track = profiles.get('auto_track', {})
    if track.get('status') == 'ACTIVE_ASSUMED_AUTO_TRACK':
        nodes = track['nodes']
        d = np.array([node['depth_m'] for node in nodes])
        z = np.array([node['z_m'] for node in nodes])
        supported = (depth >= d[0]) & (depth <= d[-1])
        floor[supported] = np.interp(depth[supported], d, z)
    height = xyz[:, 2] - floor
    points = xyz[(height >= settings['min_height_above_floor_m']) &
                 (height <= settings['max_height_above_floor_m'])]
    output = []
    for indices in voxel_components(points, settings['voxel_size_m']):
        if len(indices) < settings['min_points']:
            continue
        component = points[indices]
        if np.ptp(component[:, :2], axis=0).max() > settings['max_horizontal_extent_m']:
            continue
        output.append({'points': len(indices),
                       'kind': 'ABOVE_FLOOR_CANDIDATE_NOT_PERSON_CLASSIFICATION',
                       'nearest_distance_m': float(np.linalg.norm(component, axis=1).min()),
                       'bounds_source_coordinates': {
                           axis: {'min': float(component[:, i].min()), 'max': float(component[:, i].max())}
                           for i, axis in enumerate('xyz')}})
    return output


def evaluate_cloud(msg, config):
    """Evaluate one PointCloud2 without claiming clearance or safety validity."""
    stats, xyz = inspect_cloud(msg)
    issues = contract_issues(config, stats['frame'])
    common = {
        'source_frame': stats['frame'],
        'header_timestamp_ns': str(stats['header_ns']),
        'source_points': stats['points'],
        'finite_points': stats['finite'],
        'zero_xyz_returns': stats['zero'],
        'nonfinite_points': stats['nonfinite'],
        'geometry_basis': 'ASSUMED_HACKATHON',
        'safety_decision_permitted': False,
        'clear_decision_permitted': False,
    }
    if issues:
        return dict(common, status=UNKNOWN, reason=issues[0], clusters=[],
                    approximate_nearest_distance_m=None,
                    path_profile={'status': 'NOT_EVALUATED'})
    (in_core, in_warning, depths_all, path_profile, path_profiles, straight_warning,
     auto_grade_warning, auto_grade_core, auto_track_warning,
     auto_track_core) = candidate_envelope_masks(xyz, config)
    candidates = xyz[in_warning]
    protrusions = protrusion_clusters(candidates, config, path_profiles)
    depths = depths_all[in_warning]
    core_flags = in_core[in_warning]
    components = voxel_components(candidates, float(config['detection']['clustering']['voxel_size_m']))
    minimum = int(config['detection']['clustering']['min_cluster_points'])
    clusters = []
    for indices in components:
        if len(indices) < minimum:
            continue
        cluster_points = candidates[indices]
        cluster_depths = depths[indices]
        nearest = float(np.linalg.norm(cluster_points, axis=1).min())
        straight_here = straight_warning[in_warning][indices]
        auto_grade_here = auto_grade_warning[in_warning][indices]
        auto_track_here = auto_track_warning[in_warning][indices]
        auto_grade_core_here = auto_grade_core[in_warning][indices]
        auto_track_core_here = auto_track_core[in_warning][indices]
        active_hypotheses = []
        if bool(straight_here.any()):
            active_hypotheses.append('STRAIGHT_FALLBACK')
        if bool(auto_grade_here.any()):
            active_hypotheses.append('AUTO_GRADE')
        if bool(auto_track_here.any()):
            active_hypotheses.append('AUTO_TRACK')
        clusters.append({
            'points': int(len(indices)),
            'nearest_distance_m': nearest,
            'forward_depth_range_m': [float(cluster_depths.min()), float(cluster_depths.max())],
            'bounds_source_coordinates': {
                'x': {'min': float(cluster_points[:, 0].min()), 'max': float(cluster_points[:, 0].max())},
                'y': {'min': float(cluster_points[:, 1].min()), 'max': float(cluster_points[:, 1].max())},
                'z': {'min': float(cluster_points[:, 2].min()), 'max': float(cluster_points[:, 2].max())},
            },
            'zone': ('CORE_ASSUMED_ENVELOPE' if bool(core_flags[indices].any())
                     else 'WARNING_LAYER_ASSUMED_GEOMETRY'),
            'path_hypothesis': '_AND_'.join(active_hypotheses),
            'auto_grade_core_intersection': bool(auto_grade_core_here.any()),
            'auto_track_core_intersection': bool(auto_track_core_here.any()),
        })
    if not clusters:
        return dict(common, status=UNKNOWN, reason='NO_CLUSTER_IN_ASSUMED_ENVELOPE', clusters=[],
                    approximate_nearest_distance_m=None, path_profile=path_profile,
                    path_profiles=path_profiles, protrusion_clusters=protrusions)
    nearest = min(cluster['nearest_distance_m'] for cluster in clusters)
    has_core_candidate = any(cluster['zone'] == 'CORE_ASSUMED_ENVELOPE' for cluster in clusters)
    return dict(common,
                status=(config['activation']['candidate_result'] if has_core_candidate
                        else config['activation']['warning_candidate_result']),
                reason=('CLUSTER_INTERSECTS_ASSUMED_ENVELOPE' if has_core_candidate
                        else 'CLUSTER_INTERSECTS_ASSUMED_WARNING_LAYER'),
                clusters=sorted(clusters, key=lambda cluster: cluster['nearest_distance_m']),
                approximate_nearest_distance_m=nearest,
                approximate_distance_label=config['activation']['approximate_distance_label'],
                path_profile=path_profile, path_profiles=path_profiles, protrusion_clusters=protrusions)


def _diagnostic_array(result):
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    message = DiagnosticArray()
    status = DiagnosticStatus()
    status.name = 'lidar_mosmetro3d/stage_3_baseline'
    status.level = DiagnosticStatus.WARN
    status.message = result['status'] + ': ' + result['reason']
    status.values = [KeyValue(key=key, value=str(value)) for key, value in (
        ('geometry_basis', result['geometry_basis']),
        ('source_frame', result['source_frame']),
        ('safety_decision_permitted', result['safety_decision_permitted']),
        ('clear_decision_permitted', result['clear_decision_permitted']),
        ('cluster_count', len(result['clusters'])),
        ('auto_grade_status', result.get('path_profile', {}).get('status', 'NOT_REPORTED')),
    )]
    message.status = [status]
    return message


def processing_error_result(msg, exc):
    return {
        'status': UNKNOWN,
        'reason': 'BASELINE_PROCESSING_ERROR:' + str(exc),
        'source_frame': msg.header.frame_id,
        'header_timestamp_ns': str(msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec),
        'source_points': None,
        'finite_points': None,
        'zero_xyz_returns': None,
        'nonfinite_points': None,
        'geometry_basis': 'ASSUMED_HACKATHON',
        'safety_decision_permitted': False,
        'clear_decision_permitted': False,
        'clusters': [],
        'approximate_nearest_distance_m': None,
    }


def baseline_node_class():
    """Load ROS dependencies only when the executable node is needed."""
    from diagnostic_msgs.msg import DiagnosticArray
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import PointCloud2
    from std_msgs.msg import String

    class BaselineNode(Node):
        def __init__(self, input_topic=None, geometry_config=None, result_topic=None,
                     diagnostics_topic=None, result_jsonl_path=None):
            super().__init__('stage_3_envelope_baseline')
            self.declare_parameter('geometry_config', geometry_config or '/app/config/geometry_contract.yaml')
            self.declare_parameter('input_topic', input_topic or '/sensing/lidar/hesai128/pointcloud')
            self.declare_parameter('result_topic', result_topic or '/stage_3/obstacle_candidate')
            self.declare_parameter('diagnostics_topic', diagnostics_topic or '/stage_3/diagnostics')
            self.declare_parameter('result_jsonl_path', result_jsonl_path or '')
            self.config = load_geometry_contract(self.get_parameter('geometry_config').value)
            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.VOLATILE)
            self.result_publisher = self.create_publisher(String, self.get_parameter('result_topic').value, qos)
            self.diagnostics_publisher = self.create_publisher(
                DiagnosticArray, self.get_parameter('diagnostics_topic').value, qos)
            self.result_jsonl_path = self.get_parameter('result_jsonl_path').value
            self.subscription = self.create_subscription(
                PointCloud2, self.get_parameter('input_topic').value, self.receive, qos)

        def receive(self, msg):
            started = time.perf_counter()
            try:
                result = evaluate_cloud(msg, self.config)
            except (KeyError, TypeError, ValueError) as exc:
                result = processing_error_result(msg, exc)
            result['processing_ms'] = (time.perf_counter() - started) * 1000.0
            output = String()
            output.data = json.dumps(result, ensure_ascii=False, sort_keys=True)
            self.result_publisher.publish(output)
            self.diagnostics_publisher.publish(_diagnostic_array(result))
            if self.result_jsonl_path:
                with Path(self.result_jsonl_path).open('a', encoding='utf-8') as stream:
                    stream.write(output.data + '\n')
    return BaselineNode


def run_node():
    import rclpy

    rclpy.init()
    node = baseline_node_class()()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print-contract', action='store_true')
    parser.add_argument('--geometry-config', type=Path, default=Path('/app/config/geometry_contract.yaml'))
    args, _ = parser.parse_known_args()
    if args.print_contract:
        print(json.dumps(load_geometry_contract(args.geometry_config)['activation'], indent=2))
        return
    run_node()


if __name__ == '__main__':
    main()
