import unittest

from stage_3_metrics import summarize_window


def frame(index):
    return {
        'header_timestamp_ns': str(100 + index),
        'source_frame': 'lidar_livox',
        'bag_offset_seconds': index * 0.1,
    }


def result(index, status, processing_ms):
    return {
        'header_timestamp_ns': str(100 + index),
        'source_frame': 'lidar_livox',
        'status': status,
        'processing_ms': processing_ms,
    }


class Stage3MetricsTest(unittest.TestCase):
    def test_summarizes_candidate_rate_and_processing_percentiles(self):
        frames = [frame(index) for index in range(3)]
        results = [
            result(0, 'UNKNOWN', 10.0),
            result(1, 'OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY', 20.0),
            result(2, 'WARNING_CANDIDATE_ASSUMED_GEOMETRY', 30.0),
        ]
        summary = summarize_window(results, frames, 0, 2)
        self.assertEqual(summary['candidate_frames'], 2)
        self.assertEqual(summary['status_counts']['UNKNOWN'], 1)
        self.assertAlmostEqual(summary['candidate_rate_per_minute'], 600.0)
        self.assertEqual(summary['processing_ms']['p50'], 20.0)
        self.assertAlmostEqual(summary['processing_ms']['p95'], 29.0)

    def test_rejects_result_frame_mismatch(self):
        with self.assertRaises(ValueError):
            summarize_window([result(1, 'UNKNOWN', 1.0), result(1, 'UNKNOWN', 2.0)],
                             [frame(0), frame(1)], 0, 1)


if __name__ == '__main__':
    unittest.main()
