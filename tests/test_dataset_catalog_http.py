"""Integration test against the running local dataset catalog (stdlib only)."""
import array
import json
import math
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

BASE = 'http://localhost:8080'

def read(path):
    with urlopen(BASE + path, timeout=60) as response:
        return response.read()

def metadata(path):
    return json.loads(read(path))

class DatasetCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            read('/datasets.json')
        except URLError as error:
            raise unittest.SkipTest(
                f'local dataset catalog is not running at {BASE}: {error}'
            )

    def test_catalog_identity_and_geometry_isolation(self):
        catalog = {item['id']: item for item in metadata('/datasets.json')}
        self.assertIn('doubleT_obstacle', catalog)
        self.assertIn('new_data', catalog)
        old = metadata(catalog['doubleT_obstacle']['manifest'])
        new = metadata(catalog['new_data']['manifest'])
        self.assertEqual(old['dataset'], 'doubleT_obstacle')
        self.assertEqual(new['dataset'], 'new_data')
        self.assertTrue(new['geometry_enabled'])
        self.assertEqual(new['geometry_status'], 'EXPERIMENTAL_ASSUMED_FRAME_LOCAL_CANDIDATES_ONLY')
        self.assertIn('геометрические кандидаты', new['geometry_notice'])
        self.assertFalse(new['object_candidates_enabled'])
        self.assertEqual(new['visualization_overlay']['source_axis_assumption']['longitudinal_sign'], -1)
        self.assertEqual(new['visualization_overlay']['reference_cross_section']['vertical_extent_above_rail_m'],
                         {'min': 0.0, 'max': 3.7})
        self.assertTrue(old['frames'][0]['file'].startswith('/datasets/doubleT_obstacle/'))
        self.assertEqual(len(new['frames']), 11271)

    def test_real_begin_middle_end_and_return(self):
        for index in (0, 5635, 11270, 0):
            record = metadata(f'/api/new_data/{index}.json')
            self.assertEqual(record['index'], index)
            self.assertEqual(record['dataset_id'], 'new_data')
            self.assertEqual(record['source_frame'], 'hesai_lidar')
            data = read(record['file'])
            self.assertEqual(len(data), record['displayed_points'] * 12)
            values = array.array('f', data)
            self.assertTrue(all(math.isfinite(v) for v in values))
            self.assertEqual(record['source_points'], record['displayed_points'] + record['zero_xyz_returns'] + record['nonfinite_points'])
            print(json.dumps({k: record[k] for k in ('index','bag_offset_seconds','source_frame','source_part','displayed_points')}, ensure_ascii=False))

    def test_unlisted_paths_and_out_of_range_are_rejected(self):
        for path in ('/api/new_data/11271.json', '/api/new_data/-1.json', '/dataset/for_hackathon/new_data', '/config/geometry_contract.yaml'):
            with self.assertRaises(HTTPError) as context:
                read(path)
            self.assertEqual(context.exception.code, 404)

if __name__ == '__main__':
    unittest.main()
