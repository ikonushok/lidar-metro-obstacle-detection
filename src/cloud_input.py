"""Schema-aware PointCloud2 inspection; no geometric decisions or filtering."""
import numpy as np

FORMATS = {1: 'i1', 2: 'u1', 3: 'i2', 4: 'u2', 5: 'i4', 6: 'u4', 7: 'f4', 8: 'f8'}


def point_view(msg):
    if msg.point_step <= 0 or msg.row_step < msg.width * msg.point_step:
        raise ValueError('Invalid point_step/row_step')
    if len(msg.data) != msg.height * msg.row_step:
        raise ValueError('Data length differs from height * row_step')
    names, formats, offsets = [], [], []
    for f in msg.fields:
        if f.name in names or f.datatype not in FORMATS or f.count < 1:
            raise ValueError('Invalid or duplicate field')
        dt = np.dtype(('>' if msg.is_bigendian else '<') + FORMATS[f.datatype])
        if f.offset < 0 or f.offset + dt.itemsize * f.count > msg.point_step:
            raise ValueError('Field outside point_step')
        names.append(f.name)
        formats.append(dt if f.count == 1 else (dt, (f.count,)))
        offsets.append(f.offset)
    for axis in ('x', 'y', 'z'):
        matches = [f for f in msg.fields if f.name == axis]
        if len(matches) != 1 or matches[0].count != 1 or matches[0].datatype not in (7, 8):
            raise ValueError('XYZ must be scalar floating-point fields')
    dtype = np.dtype(dict(names=names, formats=formats, offsets=offsets, itemsize=msg.point_step))
    return np.ndarray((msg.height, msg.width), dtype=dtype, buffer=msg.data,
                      strides=(msg.row_step, msg.point_step))


def inspect_cloud(msg):
    points = point_view(msg)
    xyz = np.column_stack([points[k].ravel() for k in ('x', 'y', 'z')])
    finite = np.isfinite(xyz).all(axis=1)
    zero = (xyz == 0).all(axis=1)
    usable = xyz[finite & ~zero]
    stats = dict(points=len(xyz), finite=int(finite.sum()), zero=int(zero.sum()),
                 nonfinite=int((~finite).sum()), nonzero_finite=len(usable),
                 frame=msg.header.frame_id,
                 header_ns=msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec,
                 shape=[msg.height, msg.width], point_step=msg.point_step,
                 row_step=msg.row_step, bigendian=msg.is_bigendian,
                 fields=[[f.name, f.offset, f.datatype, f.count] for f in msg.fields],
                 xyz_min=usable.min(axis=0).tolist() if len(usable) else None,
                 xyz_max=usable.max(axis=0).tolist() if len(usable) else None)
    if 'timestamp' in points.dtype.names:
        ts = points['timestamp'].ravel()
        ts = ts[np.isfinite(ts)]
        stats['point_time_range'] = [float(ts.min()), float(ts.max())] if len(ts) else None
    return stats, usable
