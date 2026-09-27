"""Focused contracts for the portable offline component classifier."""
import importlib.util
from pathlib import Path
import struct
import unittest


SPEC = importlib.util.spec_from_file_location("train_noise_classifier", Path("scripts/train_noise_classifier.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TrainNoiseClassifierTest(unittest.TestCase):
    def test_components_and_tree_prediction(self):
        raw = struct.pack("<fffffffff", 0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 4.0, 0.0, 0.0)
        self.assertEqual(MODULE.connected_components(raw, [0, 1, 2], 0.25), [[0, 1], [2]])
        rows = [
            {"label": False, "weight": .25, "features": [1, 0, 0, 0, 1, 1, 1, 1]},
            {"label": False, "weight": .25, "features": [2, 0, 0, 0, 1, 1, 1, 1]},
            {"label": True, "weight": .25, "features": [20, 0, 0, 0, 1, 1, 1, 1]},
            {"label": True, "weight": .25, "features": [21, 0, 0, 0, 1, 1, 1, 1]},
        ]
        tree = MODULE.make_tree(rows, 0, 2, 1)
        self.assertLess(MODULE.predict_probability(tree, rows[0]["features"]), .5)
        self.assertGreaterEqual(MODULE.predict_probability(tree, rows[-1]["features"]), .5)
