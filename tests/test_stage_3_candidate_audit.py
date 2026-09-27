import unittest

from stage_3_candidate_audit import audit_source_coordinate_recurrence, full_cloud_clusters


def frame(index):
    return {'header_timestamp_ns': str(100 + index), 'source_frame': 'lidar_livox'}


def cluster(x, zone='CORE_ASSUMED_ENVELOPE'):
    return {
        'zone': zone,
        'bounds_source_coordinates': {
            'x': {'min': x, 'max': x + 0.1},
            'y': {'min': -5.1, 'max': -5.0},
            'z': {'min': 1.0, 'max': 1.1},
        },
    }


def result(index, clusters):
    return {'header_timestamp_ns': str(100 + index), 'source_frame': 'lidar_livox', 'clusters': clusters}


class Stage3CandidateAuditTest(unittest.TestCase):
    def test_far_recurring_object_outside_envelope_is_audited(self):
        import numpy as np
        points = np.array([[8., -190., -6.]] * 5 + [[8., -201., -6.]] * 5)
        clusters = full_cloud_clusters(points, .25, 5, 200.)
        self.assertEqual(len(clusters), 1)
        audit = audit_source_coordinate_recurrence(
            [result(i, clusters) for i in range(3)], [frame(i) for i in range(3)], 0, 2)
        self.assertEqual(len(audit['recurrent_groups']), 1)
        self.assertEqual(audit['recurrent_groups'][0]['bounds_source_coordinates']['y']['min'], -190.)

    def test_reports_recurring_source_coordinate_bin_without_tracking_claim(self):
        audit = audit_source_coordinate_recurrence(
            [result(0, [cluster(0.0)]), result(1, [cluster(0.1)]), result(2, [cluster(2.0)])],
            [frame(0), frame(1), frame(2)], 0, 2, voxel_size_m=0.5, min_frame_fraction=2 / 3)
        self.assertEqual(len(audit['recurrent_groups']), 1)
        recurrent = audit['recurrent_groups'][0]
        self.assertEqual(recurrent['frames_present'], [0, 1])
        self.assertAlmostEqual(recurrent['recurrence_fraction'], 2 / 3)
        self.assertIn('not tracking', audit['scope'])

    def test_rejects_result_frame_mismatch(self):
        with self.assertRaises(ValueError):
            audit_source_coordinate_recurrence([result(1, [])], [frame(0)], 0, 0)


if __name__ == '__main__':
    unittest.main()
