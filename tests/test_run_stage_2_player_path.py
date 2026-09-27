from pathlib import Path
import unittest


class RunStage2PlayerPathTest(unittest.TestCase):
    @staticmethod
    def _source():
        script = (Path(__file__).resolve().parents[1] / 'scripts' / 'run_stage_2_player.ps1')
        return script.read_text(encoding='utf-8')

    def test_stage_3_results_path_is_converted_to_container_separator(self):
        source = self._source()
        self.assertIn(
            "$stage3ResultsRelative = $stage3ResultsRelative.Replace([char]'\\', [char]'/' )",
            source,
        )

    def test_max_audit_frame_uses_manifest_end(self):
        source = self._source()
        self.assertIn("[string]$AuditLastFrame = 'max'", source)
        self.assertIn("$auditLastFrameResolved = [int]$auditManifest.frame_count - 1", source)

    def test_current_stage_3_result_is_preferred_over_legacy_overlay_replay(self):
        source = self._source()
        root_result = "$stage3Results = Join-Path $stage3Root 'stage_3_results.jsonl'"
        legacy_result = "$stage3Results = Join-Path $stage3Root 'overlay_replay/stage_3_results.jsonl'"
        self.assertIn(root_result, source)
        self.assertIn(legacy_result, source)
        self.assertLess(source.index(root_result), source.index(legacy_result))


if __name__ == '__main__':
    unittest.main()
