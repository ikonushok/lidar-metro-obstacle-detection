"""Serve archive sources lazily with matching C++ CPU JSON per frame."""

import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

from archive_bag_frames import ArchiveBagFrames
from cpu_catalog_runtime import CpuCatalogRuntime, DirectDetailedCpuRuntime


SOURCES = (
    ('new_data', 'new_data · 20 минут', 'new_data', 'dataset/for_hackathon/new_data'),
    ('roundT_doubleT', 'roundT_doubleT · 25 с', 'for_hackathon/roundT_doubleT', 'dataset/for_hackathon/for_hackathon'),
    ('squareT_platform_squareT_switch', 'squareT_platform_squareT_switch · 88 с',
     'for_hackathon/squareT_platform_squareT_switch', 'dataset/for_hackathon/for_hackathon'),
    ('doubleT_platform', 'doubleT_platform · 34 с', 'for_hackathon/doubleT_platform',
     'dataset/for_hackathon/for_hackathon'),
    ('roundT_squareT_pressureGate_squareT', 'roundT_squareT_pressureGate_squareT · 55 с',
     'for_hackathon/roundT_squareT_pressureGate_squareT', 'dataset/for_hackathon/for_hackathon'),
    ('doubleT_obstacle', 'doubleT_obstacle · 20 с · assumed geometry',
     'for_hackathon/doubleT_obstacle', 'dataset/for_hackathon/for_hackathon'),
    ('roundT_pressureGate_roundT', 'roundT_pressureGate_roundT · 27 с',
     'for_hackathon/roundT_pressureGate_roundT', 'dataset/for_hackathon/for_hackathon'),
    ('cloud_with_fake_obj', 'cloud_with_fake_obj · fake obstacle',
     'cloud_with_fake_obj', 'dataset/for_hackathon/cloud_with_fake_obj'),
)

class StaleFrameRequest(Exception):
    """Raised when a newer frame request supersedes the current one."""


def load_obstacle_annotations(root: Path):
    """Load evaluator-only anchors; they are never passed to the C++ runtime."""
    path = root / 'config/obstacle_annotations_development.json'
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding='utf-8'))
    if document.get('detector_input_permitted') is not False:
        raise ValueError('obstacle annotations must remain evaluator-only')
    dataset = document.get('dataset')
    by_frame = {}
    for item in document.get('point_annotations', []):
        if not isinstance(item.get('frame_index'), int):
            raise ValueError('obstacle annotation frame_index must be an integer')
        by_frame.setdefault(item['frame_index'], []).append(item)
    return {dataset: by_frame} if dataset else {}


def viewer_result(result):
    """Return the ordinary player result without heavy debug-only point lists."""
    value = dict(result)
    value.pop('outside_reference_source_indices', None)
    return value


def load_review_objects(root: Path):
    """Expose user-visible windows without changing legacy event-score windows."""
    document = json.loads((root / 'config/evaluation_labels.json').read_text(encoding='utf-8'))
    return [{**item, 'frames_inclusive': item.get('visible_frames_inclusive')}
            for item in document['review_object_catalog']]


def load_review_source_statuses(root: Path):
    """Read evaluator-only source status for display, never detector input."""
    document = json.loads((root / 'config/evaluation_labels.json').read_text(encoding='utf-8'))
    return {item['source_id']: item.get('label_status') for item in document['sources']}


def load_local_review_alarm_frames(root: Path, frame_count: int, mode: str):
    """Optional ignored replay evidence; never an input to the detector."""
    path = root / 'docs/stages/fake_object_frame_review.json'
    if not path.exists():
        return []
    try:
        report = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    if (report.get('format') != 'fake_object_frame_review_v1'
            or report.get('dataset') != 'cloud_with_fake_obj'
            or report.get('mode') != mode
            or report.get('frame_count') != frame_count):
        return []
    return [frame['index'] for frame in report.get('frames', [])
            if frame.get('alarm') is True and isinstance(frame.get('index'), int)
            and 0 <= frame['index'] < frame_count]


def serve(root: Path, port: int, rail_selection_method: str, rail_forward_min_m: float,
          forward_extension_method: str, arc_extension_horizon_m: float,
          min_arc_radius_m: float, max_arc_turn_deg: float, arc_fit_window_pairs: int,
          noise_filter_mode: str):
    sources = {source_id: ArchiveBagFrames(root / archive, prefix, source_id)
               for source_id, _label, prefix, archive in SOURCES}
    labels = {source_id: label for source_id, label, _prefix, _archive in SOURCES}
    runtime_class = DirectDetailedCpuRuntime if rail_selection_method == 'development_candidate' else CpuCatalogRuntime
    runtime = runtime_class(rail_selection_method=rail_selection_method,
                                 rail_forward_min_m=rail_forward_min_m,
                                 forward_extension_method=forward_extension_method,
                                 arc_extension_horizon_m=arc_extension_horizon_m,
                                 min_arc_radius_m=min_arc_radius_m,
                                 max_arc_turn_deg=max_arc_turn_deg,
                                 arc_fit_window_pairs=arc_fit_window_pairs,
                                 noise_filter_mode=noise_filter_mode)
    result_cache = OrderedDict()
    active_source = None
    obstacle_annotations = load_obstacle_annotations(root)
    review_objects = load_review_objects(root)
    review_source_statuses = load_review_source_statuses(root)
    review_alarm_frames = load_local_review_alarm_frames(
        root, len(sources['cloud_with_fake_obj'].lookup),
        f'{rail_selection_method}/fmin{rail_forward_min_m:g}/{forward_extension_method}/{noise_filter_mode}')
    latest_frame_tokens = {}
    state_lock = threading.Lock()
    data_lock = threading.Lock()
    runtime_lock = threading.Lock()

    def manifest(source_id):
        source = sources[source_id]
        return {
            'format': 'lidar-cpu-catalog-v1', 'dataset': labels[source_id], 'dataset_id': source_id,
            'frame_count': len(source.lookup), 'safety_decision_permitted': False,
            'compute_backend': 'cpu', 'rail_selection_method': rail_selection_method,
            'runtime_transport': runtime.runtime_transport,
            'rail_search_config': runtime.rail_search_config,
            'forward_extension_config': runtime.forward_extension_config,
            'noise_filter_mode': noise_filter_mode,
            'runtime_noise_filter_mode': runtime.noise_filter_mode,
            'playback_timing': 'SOURCE_BAG_TIMING_PLUS_LAZY_CPU_PROCESSING',
            'review_objects': review_objects if source_id == 'cloud_with_fake_obj' else [],
            'review_label_status': review_source_statuses.get(source_id),
            'review_alarm_frames': review_alarm_frames if source_id == 'cloud_with_fake_obj' else [],
            'review_alarm_frames_source': 'ignored_offline_replay' if review_alarm_frames else None,
            'review_labels_are_detector_input': False,
            'frames': [{'index': index, 'source_index': index,
                        'metadata_url': f'/api/cpu_sources/{source_id}/{index}.json'}
                       for index in range(len(source.lookup))],
        }

    def mark_latest_frame_request(source_id, index):
        token = object()
        with state_lock:
            latest_frame_tokens[source_id] = (index, token)
        return token

    def ensure_latest_frame_request(source_id, index, token):
        with state_lock:
            if latest_frame_tokens.get(source_id) != (index, token):
                raise StaleFrameRequest()

    def frame_result(source_id, index, token):
        nonlocal active_source
        if source_id not in sources:
            raise IndexError('Unknown source')
        key = (source_id, index)
        with data_lock:
            if active_source is not None and active_source != source_id:
                sources[active_source].release()
            active_source = source_id
            record, xyz = sources[source_id].frame(index)
            if key in result_cache:
                result_cache.move_to_end(key)
                return record, xyz, result_cache[key]
        ensure_latest_frame_request(source_id, index, token)
        with runtime_lock:
            ensure_latest_frame_request(source_id, index, token)
            result = runtime.analyze(record, xyz)
        ensure_latest_frame_request(source_id, index, token)
        with data_lock:
            result_cache[key] = result
            while len(result_cache) > 3:
                result_cache.popitem(last=False)
            return record, xyz, result

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/datasets.json':
                    return self.send_json([{'id': source_id, 'label': label,
                                            'manifest': f'/api/cpu_sources/{source_id}/manifest.json'}
                                           for source_id, label, _prefix, _archive in SOURCES])
                if path == '/manifest.json':
                    return self.send_json(manifest('new_data'))
                match = re.fullmatch(r'/api/cpu_sources/([A-Za-z0-9_-]+)/(manifest\.json|(\d+)\.(json|xyzf))', path)
                if match:
                    source_id, suffix = match[1], match[2]
                    if source_id not in sources:
                        return self.send_error(404)
                    if suffix == 'manifest.json':
                        return self.send_json(manifest(source_id))
                    index, kind = int(match[3]), match[4]
                    token = mark_latest_frame_request(source_id, index)
                    record, xyz, result = frame_result(source_id, index, token)
                    if kind == 'xyzf':
                        return self.send_bytes(xyz)
                    record = dict(record)
                    record['file'] = f'/api/cpu_sources/{source_id}/{index}.xyzf'
                    review_annotations = obstacle_annotations.get(source_id, {}).get(index, [])
                    return self.send_json({'frame': record, 'result': viewer_result(result),
                                           'review_annotations': review_annotations,
                                           'review_annotations_are_detector_input': False})
                # Saved new_data links remain usable.
                match = re.fullmatch(r'/api/cpu_new_data/(\d+)\.(json|xyzf)', path)
                if match:
                    index, kind = int(match[1]), match[2]
                    token = mark_latest_frame_request('new_data', index)
                    record, xyz, result = frame_result('new_data', index, token)
                    if kind == 'xyzf':
                        return self.send_bytes(xyz)
                    record = dict(record)
                    record['file'] = f'/api/cpu_new_data/{index}.xyzf'
                    return self.send_json({'frame': record, 'result': viewer_result(result)})
                if path in ('/', '/index.html'):
                    html = (root / 'web/stage_4_cpu_viewer.html').read_text(encoding='utf-8').replace(
                        '<script src="stage_4_cpu_player.js"></script>',
                        '<script src="stage_4_cpu_player_source_selector.js"></script>'
                        '<script src="stage_4_cpu_player.js"></script>')
                    return self.send_bytes(html.encode(), 'text/html; charset=utf-8')
                if path == '/stage_4_cpu_player_source_selector.js':
                    return self.send_bytes((root / 'web/stage_4_cpu_player_source_selector.js').read_bytes(), 'text/javascript')
                if path == '/stage_4_cpu_player.js':
                    return self.send_bytes((root / 'web/stage_4_cpu_player.js').read_bytes(), 'text/javascript')
                if path == '/stage_4_cpu_player_events.js':
                    return self.send_bytes((root / 'web/stage_4_cpu_player_events.js').read_bytes(), 'text/javascript')
                if path == '/stage_4_cpu_player_controls.js':
                    return self.send_bytes((root / 'web/stage_4_cpu_player_controls.js').read_bytes(), 'text/javascript')
                if path == '/stage_4_cpu_player_axis_labels.js':
                    return self.send_bytes((root / 'web/stage_4_cpu_player_axis_labels.js').read_bytes(), 'text/javascript')
                if path in ('/vendor/three.min.js', '/vendor/OrbitControls.js'):
                    return self.send_bytes((root / 'artefacts/stage_4/cpu_viewer' / path[1:]).read_bytes(), 'text/javascript')
                self.send_error(404)
            except StaleFrameRequest:
                self.send_error(409, 'Stale frame request superseded by a newer frame')
            except (IndexError, FileNotFoundError):
                self.send_error(404)
            except Exception as error:
                print(type(error).__name__, str(error), flush=True)
                self.send_error(500, 'CPU catalog frame processing failed; no frame committed')

        def send_json(self, value):
            self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), 'application/json')

        def send_bytes(self, data, mime='application/octet-stream'):
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    try:
        server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
        server.daemon_threads = True
        server.serve_forever()
    finally:
        runtime.close()
        for source in sources.values():
            source.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/workspace'))
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--rail-selection-method', choices=('baseline', 'development_candidate'),
                        default='development_candidate')
    parser.add_argument('--rail-forward-min-m', type=float, default=2.0)
    parser.add_argument('--forward-extension-method', choices=('tangent', 'arc_limited'), default='tangent')
    parser.add_argument('--arc-extension-horizon-m', type=float, default=0.0)
    parser.add_argument('--min-arc-radius-m', type=float, default=60.0)
    parser.add_argument('--max-arc-turn-deg', type=float, default=8.0)
    parser.add_argument('--arc-fit-window-pairs', type=int, default=5)
    parser.add_argument('--noise-filter-mode', choices=('legacy', 'baseline_v3_assist_score', 'baseline_v3'),
                        default='baseline_v3')
    args = parser.parse_args()
    serve(args.root, args.port, args.rail_selection_method, args.rail_forward_min_m,
          args.forward_extension_method, args.arc_extension_horizon_m,
          args.min_arc_radius_m, args.max_arc_turn_deg,
          args.arc_fit_window_pairs, args.noise_filter_mode)
