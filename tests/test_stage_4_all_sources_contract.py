"""Static contract for the all-source C++ CPU viewer."""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_sources():
    server = ROOT / 'scripts/serve_stage_2_cpu_catalog.py'
    tree = ast.parse(server.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'SOURCES'
                                                for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('SOURCES assignment not found')


class AllSourcesViewerContractTests(unittest.TestCase):
    def test_exact_source_inventory_and_archive_boundaries(self):
        SOURCES = load_sources()
        ids = [row[0] for row in SOURCES]
        self.assertEqual(ids, [
            'new_data', 'roundT_doubleT', 'squareT_platform_squareT_switch',
            'doubleT_platform', 'roundT_squareT_pressureGate_squareT',
            'doubleT_obstacle', 'roundT_pressureGate_roundT',
            'cloud_with_fake_obj',
        ])
        self.assertEqual(SOURCES[0][3], 'dataset/for_hackathon/new_data')
        self.assertTrue(all(row[3] == 'dataset/for_hackathon/for_hackathon' for row in SOURCES[1:7]))
        self.assertEqual(SOURCES[7][3], 'dataset/for_hackathon/cloud_with_fake_obj')
        self.assertEqual(SOURCES[5][1], 'doubleT_obstacle · 20 с · assumed geometry')
        self.assertEqual(SOURCES[7][1], 'cloud_with_fake_obj · fake obstacle')

    def test_viewer_selector_only_routes_to_server_catalog(self):
        selector = (ROOT / 'web/stage_4_cpu_player_source_selector.js').read_text(encoding='utf-8')
        self.assertIn('nativeFetch("/datasets.json"', selector)
        self.assertIn("/api/cpu_sources/", selector)
        self.assertIn('const selected=/^[A-Za-z0-9_-]+$/.test(requested||"")?requested:null', selector)
        self.assertIn('if(selected&&!ids.has(selected))throw Error(', selector)
        self.assertIn("window.cpuCatalogSelectedSource=selected", selector)
        self.assertTrue("option.textContent='Выберите датасет'" in selector or
                        'option.textContent="Выберите датасет"' in selector or
                        'option.textContent="�������� �������"' in selector)
        self.assertNotIn("selected=ids.has(requested)?requested:'new_data'", selector)
        self.assertNotIn('AutoRails', selector)
        self.assertNotIn('CurveEnvelope', selector)
        self.assertNotIn('createEnvelope(', selector)

    def test_player_does_not_autoload_default_dataset_without_selection(self):
        player = (ROOT / 'web/stage_4_cpu_player.js').read_text(encoding='utf-8')
        self.assertIn('if(!window.cpuCatalogSelectedSource)', player)
        self.assertIn("Датасет не выбран. C++ расчёт не запущен.", player)
        self.assertIn("else fetch('manifest.json')", player)

    def test_control_obstacles_are_evaluator_only_and_semantic_free(self):
        document = json.loads((ROOT / 'config/obstacle_annotations_development.json').read_text(encoding='utf-8'))
        self.assertEqual(document['dataset'], 'doubleT_obstacle')
        self.assertIs(document['detector_input_permitted'], False)
        annotations = {item['frame_index']: item for item in document['point_annotations']}
        self.assertEqual(sorted(annotations), [55, 160])
        for annotation in annotations.values():
            self.assertEqual(annotation['label'], 'Контрольная помеха')
            self.assertNotIn('semantic_class', annotation)
        player = (ROOT / 'web/stage_4_cpu_player.js').read_text(encoding='utf-8')
        self.assertIn('review_annotations_are_detector_input!==false', player)
        self.assertIn('CORE_INTERSECTION', player)
        self.assertIn('UNKNOWN', player)

    def test_frame_slider_debounces_cpp_requests(self):
        player = (ROOT / 'web/stage_4_cpu_player.js').read_text(encoding='utf-8')
        self.assertIn('frameSeekDebounceMs=350', player)
        self.assertIn("seekFromSlider(true)", player)
        self.assertIn("seekFromSlider(false)", player)
        self.assertIn("setTimeout(()=>{seekTimer=null;show(index)},frameSeekDebounceMs)", player)
        self.assertNotIn("$('frame-range').oninput=()=>{pause();show(", player)

    def test_server_drops_stale_frame_requests(self):
        server = (ROOT / 'scripts/serve_stage_2_cpu_catalog.py').read_text(encoding='utf-8')
        self.assertIn('ThreadingHTTPServer', server)
        self.assertIn('class StaleFrameRequest(Exception):', server)
        self.assertIn('latest_frame_tokens[source_id] = (index, token)', server)
        self.assertIn('raise StaleFrameRequest()', server)
        self.assertIn('with runtime_lock:', server)
        self.assertIn("self.send_error(409, 'Stale frame request superseded by a newer frame')", server)

    def test_viewer_json_omits_heavy_outside_reference_indices(self):
        server = (ROOT / 'scripts/serve_stage_2_cpu_catalog.py').read_text(encoding='utf-8')
        self.assertIn('def viewer_result(result):', server)
        self.assertIn("value.pop('outside_reference_source_indices', None)", server)
        self.assertIn("'result': viewer_result(result)", server)


if __name__ == '__main__':
    unittest.main()
