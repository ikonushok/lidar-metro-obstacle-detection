"""Fail-closed metrics for a declared Stage 3 development frame window."""

import math

import numpy as np


CANDIDATE_STATUSES = {
    'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY',
    'WARNING_CANDIDATE_ASSUMED_GEOMETRY',
}


def summarize_window(results, frames, first_frame, last_frame):
    """Return processing and candidate metrics without treating the window as truth."""
    if len(results) != len(frames):
        raise ValueError('results and manifest frames must have equal length')
    if first_frame < 0 or last_frame < first_frame or last_frame >= len(frames):
        raise ValueError('frame window is outside the manifest')
    selected_results = results[first_frame:last_frame + 1]
    selected_frames = frames[first_frame:last_frame + 1]
    if any(str(result.get('header_timestamp_ns')) != str(frame['header_timestamp_ns'])
           or result.get('source_frame') != frame['source_frame']
           for result, frame in zip(selected_results, selected_frames)):
        raise ValueError('results do not match manifest frames')
    offsets = [float(frame['bag_offset_seconds']) for frame in selected_frames]
    duration = offsets[-1] - offsets[0]
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('frame window must have positive bag-time duration')
    processing = np.asarray([float(result['processing_ms']) for result in selected_results], dtype=float)
    if not np.isfinite(processing).all() or (processing < 0).any():
        raise ValueError('processing_ms must be finite and non-negative')
    statuses = {status: sum(result.get('status') == status for result in selected_results)
                for status in sorted({result.get('status') for result in selected_results})}
    candidates = sum(result.get('status') in CANDIDATE_STATUSES for result in selected_results)
    return {
        'frame_window_inclusive': [first_frame, last_frame],
        'frames': len(selected_results),
        'bag_duration_seconds': duration,
        'candidate_frames': candidates,
        'candidate_rate_per_minute': candidates * 60.0 / duration,
        'status_counts': statuses,
        'processing_ms': {
            'p50': float(np.percentile(processing, 50)),
            'p95': float(np.percentile(processing, 95)),
            'min': float(processing.min()),
            'max': float(processing.max()),
        },
        'scope': ('DEVELOPMENT_ONLY: visual clean candidate, not a labelled negative set; '
                  'processing duration only, not end-to-end latency'),
    }
