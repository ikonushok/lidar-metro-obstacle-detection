"""Focused contracts for the hidden rail-tail benchmark helpers."""
import importlib.util
import math
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace


SPEC = importlib.util.spec_from_file_location(
    "benchmark_hidden_rail_tail", Path("scripts/benchmark_hidden_rail_tail.py"))
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def centres(offset: float = 0.0):
    return [
        MODULE.Center(float(index), 0.05 * (index + offset) ** 2, -float(index), 0.0)
        for index in range(10)
    ]


class HiddenRailTailBenchmarkTest(unittest.TestCase):
    def test_tangent_and_arc_return_predictions(self):
        prefix = centres()[:7]
        target_s = centres()[7].source_s_m
        tangent = MODULE.tangent_predict(prefix, target_s)
        arc = MODULE.arc_predict(prefix, target_s, window=5)
        self.assertIsNotNone(tangent)
        self.assertIsNotNone(arc)
        self.assertEqual(tangent.source_s_m, target_s)
        self.assertEqual(arc.source_s_m, target_s)

    def test_arc_clamp_can_decline_prediction(self):
        prefix = centres()[:7]
        prediction = MODULE.arc_predict(prefix, centres()[9].source_s_m, window=5,
                                        min_radius_m=10_000.0, max_turn_deg=1.0)
        self.assertIsNone(prediction)

    def test_ridge_model_predicts_tail_shape(self):
        train = [centres(offset / 10.0) for offset in range(5)]
        model = MODULE.train_ridge_step_model(train, ridge_lambda=1e-3)
        prefix = centres(0.25)[:7]
        prediction = MODULE.ml_predict(prefix, centres(0.25)[7].source_s_m, model)
        self.assertIsNotNone(prediction)
        self.assertLess(math.hypot(prediction.x - centres(0.25)[7].x,
                                   prediction.y - centres(0.25)[7].y), 0.25)

    def test_run_benchmark_summarizes_methods(self):
        frames = [{"frame": index, "centers": centres(index / 20.0),
                   "observed_rail_pair_count": 10} for index in range(8)]
        args = SimpleNamespace(source="synthetic", first=0, last=7, rail_forward_min_m=2.0,
                               hide_pairs=2, min_prefix_pairs=4, train_fraction=0.5,
                               ridge_lambda=1e-3, min_arc_radius_m=1.0,
                               max_arc_turn_deg=30.0, arc_fit_window_pairs=5)
        report = MODULE.run_benchmark(frames, args)
        self.assertEqual(report["format"], "hidden-rail-tail-benchmark-v1")
        self.assertIn("ml_ridge_step", report["summary"])
        self.assertGreater(report["summary"]["tangent"]["target_count"], 0)


if __name__ == "__main__":
    unittest.main()
