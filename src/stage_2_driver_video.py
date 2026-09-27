"""Pure helpers for the visual-only stage 2 driver-view video."""

import numpy as np


AXIS_NAMES = ('x', 'y', 'z')


def axis_roles(assumption):
    roles = {}
    for role in ('longitudinal', 'lateral', 'vertical'):
        axis = assumption[role + '_axis']
        if axis not in AXIS_NAMES:
            raise ValueError('%s_axis must be one of %s' % (role, AXIS_NAMES))
        roles[role] = AXIS_NAMES.index(axis)
    if len(set(roles.values())) != 3:
        raise ValueError('longitudinal, lateral, and vertical axes must be distinct')
    return roles


def display_sample(xyz, maximum):
    if maximum < 1:
        raise ValueError('maximum must be positive')
    if len(xyz) <= maximum:
        return xyz
    return xyz[np.linspace(0, len(xyz) - 1, maximum, dtype=int)]


def driver_projection(xyz, roles, forward_sign, minimum_depth_m, maximum_depth_m):
    """Project source points onto a visual-only forward-facing screen."""
    if minimum_depth_m <= 0 or maximum_depth_m <= minimum_depth_m:
        raise ValueError('depth range must be positive and increasing')
    if forward_sign not in (-1, 1):
        raise ValueError('forward_sign must be -1 or 1')
    depth = forward_sign * xyz[:, roles['longitudinal']]
    mask = np.isfinite(xyz).all(axis=1) & (depth >= minimum_depth_m) & (depth <= maximum_depth_m)
    visible = xyz[mask]
    visible_depth = depth[mask]
    if not len(visible):
        return np.empty((0, 2)), np.empty((0,))
    horizontal = visible[:, roles['lateral']] / visible_depth
    vertical = visible[:, roles['vertical']] / visible_depth
    return np.column_stack((horizontal, vertical)), visible_depth


def reference_gates(roles, placement, reference, depths_m=(5.0, 10.0, 20.0, 40.0)):
    """Project rectangular universal-envelope gates into the driver view."""
    del roles  # The projection is expressed in semantic lateral/vertical coordinates.
    lateral = (placement['track_centerline_lateral_m'] + reference['lateral_min_m'],
               placement['track_centerline_lateral_m'] + reference['lateral_max_m'])
    vertical = (placement['rail_head_vertical_m'] + reference['vertical_min_m'],
                placement['rail_head_vertical_m'] + reference['vertical_max_m'])
    gates = []
    for depth in depths_m:
        if depth < placement['forward_start_m'] or depth > placement['forward_end_m']:
            continue
        gates.append((
            [lateral[0] / depth, lateral[1] / depth, lateral[1] / depth,
             lateral[0] / depth, lateral[0] / depth],
            [vertical[0] / depth, vertical[0] / depth, vertical[1] / depth,
             vertical[1] / depth, vertical[0] / depth],
        ))
    return gates
