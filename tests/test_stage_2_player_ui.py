from pathlib import Path
import unittest


class Stage2PlayerUiTest(unittest.TestCase):
    def test_recurrence_audit_is_yellow_and_not_a_safety_decision(self):
        page = (Path(__file__).resolve().parents[1] / 'web' / 'stage_2_player.html').read_text(encoding='utf-8')
        self.assertIn('0xffc34d', page)
        self.assertIn('alwaysVisible = false', page)
        self.assertIn('depthTest: !alwaysVisible', page)
        self.assertIn('ACTIVE_ASSUMED_AUTO_GRADE', page)
        self.assertIn('ACTIVE_ASSUMED_AUTO_TRACK', page)
        self.assertIn('function straightRailCenterline(overlay)', page)
        self.assertIn('buildTrackGrid(straightRailCenterline(manifest.visualization_overlay))', page)
        self.assertIn('общей прямой reference-оси −Y', page)
        self.assertIn('verticalOffset = 0', page)
        self.assertIn('renderReferenceProfile(stage3Result)', page)
        self.assertIn('renderFloorGrid(stage3Result)', page)
        self.assertNotIn('buildTrackGrid(track)', page)
        self.assertIn('не safety decision', page)


if __name__ == '__main__':
    unittest.main()
