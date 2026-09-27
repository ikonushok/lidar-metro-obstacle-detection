import json
from pathlib import Path
import tempfile
import unittest

from stage_2_player import load_stage_3_results


def record():
    return {'header_timestamp_ns': '5', 'source_frame': 'lidar_livox'}


class Stage2PlayerResultsTest(unittest.TestCase):
    def test_attaches_matching_non_safety_result(self):
        result = {
            'status': 'WARNING_CANDIDATE_ASSUMED_GEOMETRY',
            'reason': 'CLUSTER_INTERSECTS_ASSUMED_WARNING_LAYER',
            'geometry_basis': 'ASSUMED_HACKATHON',
            'safety_decision_permitted': False,
            'clear_decision_permitted': False,
            'header_timestamp_ns': '5',
            'source_frame': 'lidar_livox',
            'clusters': [],
            'protrusion_clusters': [{'points': 5, 'kind': 'ABOVE_FLOOR_CANDIDATE_NOT_PERSON_CLASSIFICATION'}],
            'path_profile': {'status': 'ACTIVE_ASSUMED_AUTO_TRACK', 'nodes': [
                {'depth_m': 5, 'x_m': 0, 'y_m': -5, 'z_m': -2},
                {'depth_m': 15, 'x_m': 1, 'y_m': -15, 'z_m': -3}]},
            'path_profiles': {'auto_grade': {'status': 'ACTIVE_ASSUMED_AUTO_GRADE',
                'z_intercept_m': -1.5, 'grade_m_per_m': -0.1}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results.jsonl'
            path.write_text(json.dumps(result) + '\n', encoding='utf-8')
            records = [record()]
            self.assertTrue(load_stage_3_results(path, records))
        self.assertEqual(records[0]['stage_3_baseline']['status'], result['status'])
        self.assertEqual(records[0]['stage_3_baseline']['protrusion_clusters'], result['protrusion_clusters'])
        self.assertEqual(records[0]['stage_3_baseline']['path_profile'], result['path_profile'])
        self.assertEqual(records[0]['stage_3_baseline']['path_profiles'], result['path_profiles'])

    def test_rejects_safety_result(self):
        result = {
            'status': 'WARNING_CANDIDATE_ASSUMED_GEOMETRY',
            'safety_decision_permitted': True,
            'clear_decision_permitted': False,
            'header_timestamp_ns': '5', 'source_frame': 'lidar_livox',
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results.jsonl'
            path.write_text(json.dumps(result) + '\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_stage_3_results(path, [record()])


if __name__ == '__main__':
    unittest.main()
