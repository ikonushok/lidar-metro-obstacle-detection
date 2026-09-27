"""Regression contract for the C++ CPU viewer launcher window."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'scripts' / 'run_stage_2_cpu_player.ps1'


class CpuPlayerLauncherTest(unittest.TestCase):
    def test_launcher_isolates_ros2_runtime_by_viewer_port(self):
        source = LAUNCHER.read_text(encoding='utf-8')
        self.assertIn('$rosDomainId = ($Port % 232) + 1', source)
        self.assertIn('-e ROS_DOMAIN_ID=$rosDomainId', source)

    def test_development_candidate_player_keeps_direct_cpp_transport(self):
        source = LAUNCHER.read_text(encoding='utf-8')
        self.assertIn("[string]$RailSelectionMethod = 'development_candidate'", source)
        self.assertIn(
            "$runtimeTransport = if ($RailSelectionMethod -eq 'development_candidate') "
            "{ 'direct_cpp' } else { 'ros2' }",
            source,
        )
        self.assertIn('$name = "lidar-cpu-catalog-$Port-$runtimeTransport-', source)

    def test_ros2_transport_remains_a_separate_non_default_path(self):
        source = LAUNCHER.read_text(encoding='utf-8')
        self.assertIn("[ValidateSet('baseline', 'development_candidate')]", source)
        self.assertIn("{ 'direct_cpp' } else { 'ros2' }", source)
        self.assertIn('--rail-selection-method $RailSelectionMethod', source)
        self.assertIn('--noise-filter-mode $NoiseFilterMode', source)

    def test_launcher_exposes_near_rail_search_boundary(self):
        source = LAUNCHER.read_text(encoding='utf-8')
        self.assertRegex(source, r'\[double\]\s*\$RailForwardMinM\s*=')
        self.assertRegex(source, r'\[double\]\s*\$RailForwardMinM\s*=\s*2\.0')
        self.assertIn('--rail-forward-min-m $RailForwardMinM', source)

    def test_launcher_exposes_explicit_forward_extension_mode(self):
        source = LAUNCHER.read_text(encoding='utf-8')
        self.assertIn("[ValidateSet('tangent', 'arc_limited')]", source)
        self.assertNotIn("'arc_clamped'", source)
        self.assertRegex(source, r'\[double\]\s*\$ArcExtensionHorizonM\s*=\s*0\.0')
        self.assertRegex(source, r'\[double\]\s*\$MinArcRadiusM\s*=\s*60\.0')
        self.assertRegex(source, r'\[double\]\s*\$MaxArcTurnDeg\s*=\s*8\.0')
        self.assertRegex(source, r'\[int\]\s*\$ArcFitWindowPairs\s*=\s*5')
        self.assertIn('--forward-extension-method $ForwardExtensionMethod', source)
        self.assertIn('--arc-extension-horizon-m $ArcExtensionHorizonM', source)
        self.assertIn('--min-arc-radius-m $MinArcRadiusM', source)
        self.assertIn('--max-arc-turn-deg $MaxArcTurnDeg', source)
        self.assertIn('--arc-fit-window-pairs $ArcFitWindowPairs', source)


if __name__ == '__main__':
    unittest.main()
