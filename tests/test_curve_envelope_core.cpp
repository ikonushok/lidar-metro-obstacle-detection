#include "curve_envelope_core.hpp"

#include <cassert>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

using lidar_mosmetro3d::AnalyzeCurveEnvelope;
using lidar_mosmetro3d::ApplyBaselineV3;
using lidar_mosmetro3d::ApplyCandidateBaselineV2;
using lidar_mosmetro3d::Bounds;
using lidar_mosmetro3d::BuildCurveEnvelopeWireframe;
using lidar_mosmetro3d::ExtendRailPairsForwardArcLimited;
using lidar_mosmetro3d::ExtendRailPairsForwardArcClamped;
using lidar_mosmetro3d::ExtendRailPairsForward;
using lidar_mosmetro3d::FrozenNoiseTreeV1Profile;
using lidar_mosmetro3d::Point3f;
using lidar_mosmetro3d::RailPair;
using lidar_mosmetro3d::Zone;

int main() {
  const std::vector<RailPair> pairs{
      {4.0, {-1.0F, -4.0F, 0.0F}, {1.0F, -4.0F, 0.0F}},
      {6.0, {-1.1F, -6.0F, 0.0F}, {0.9F, -6.0F, 0.0F}},
      {8.0, {-1.5F, -8.0F, 0.0F}, {0.5F, -8.0F, 0.0F}},
  };
  const Bounds core{-1.4, 1.4, 0.0, 3.7};
  const Bounds expanded{-1.9, 1.9, -0.5, 4.2};
  const std::vector<float> raw{
      0.0F, -4.5F, 0.005F,  // low core singleton
      1.7F, -4.5F, 1.0F,    // margin
      2.2F, -4.5F, 1.0F,    // outside reference
      0.0F, -3.9F, 1.0F,    // before first segment: UNKNOWN
      -0.8F, -9.0F, 1.0F,   // after final segment: UNKNOWN
  };
  const auto result = AnalyzeCurveEnvelope(raw.data(), raw.size() / 3, pairs, core, expanded);
  assert(result.core_count == 1 && result.margin_count == 1);
  assert(result.outside_reference_count == 1 && result.unknown_count == 2);
  assert(result.labels[0] == Zone::kCore && result.labels[1] == Zone::kMargin);
  assert(result.labels[2] == Zone::kOutsideReference);
  assert(result.labels[3] == Zone::kUnknown && result.labels[4] == Zone::kUnknown);
  assert(result.nearest_core.source_index == 0);
  assert(std::abs(result.nearest_core.distance_from_source_origin_m - std::hypot(0.0, -4.5, 0.005)) < 1e-6);
  assert(result.reportable_core_count == 0);
  assert(result.ignored_noise_count == 1);
  assert(result.ignored_noise_source_indices.size() == 1 && result.ignored_noise_source_indices[0] == 0);
  assert(result.nearest_reportable_core.source_index == std::numeric_limits<std::size_t>::max());

  std::vector<float> dense_core;
  for (int index = 0; index < 10; ++index) {
    dense_core.insert(dense_core.end(), {0.80F, static_cast<float>(-4.0 - index * 0.12), 0.10F});
  }
  for (int index = 0; index < 22; ++index) {
    dense_core.insert(dense_core.end(), {0.20F, static_cast<float>(-5.0 - index * 0.01), 0.20F});
  }
  dense_core.insert(dense_core.end(), {1.20F, -4.50F, 0.100F});  // isolated CORE noise
  const auto dense_result = AnalyzeCurveEnvelope(
      dense_core.data(), dense_core.size() / 3, pairs, core, expanded);
  assert(dense_result.reportable_core_count == 22);
  assert(dense_result.ignored_noise_count == dense_result.core_count - dense_result.reportable_core_count);
  assert(dense_result.ignored_noise_count >= 10);
  assert(dense_result.reportable_core_source_indices.size() == 22);
  assert(dense_result.ignored_noise_source_indices.size() == dense_result.ignored_noise_count);
  assert(dense_result.nearest_reportable_core.source_index >= 10);
  assert(dense_result.nearest_reportable_core.source_index < 32);

  std::vector<float> model_chain;
  for (int ix = 0; ix < 6; ++ix) {
    for (int iy = 0; iy < 5; ++iy) {
      for (int iz = 0; iz < 5; ++iz) {
        model_chain.insert(model_chain.end(), {
            static_cast<float>(ix * 0.16),
            static_cast<float>(55.0 + iy * 0.10),
            static_cast<float>(iz * 0.20)});
      }
    }
  }
  model_chain.insert(model_chain.end(), {8.0F, 8.0F, 0.0F});
  lidar_mosmetro3d::AnalysisResult model_input;
  model_input.labels.assign(model_chain.size() / 3, Zone::kCore);
  model_input.core_count = model_input.labels.size();
  FrozenNoiseTreeV1Profile model_profile;
  ApplyCandidateBaselineV2(
      model_chain.data(), model_chain.size() / 3, model_input, 0.25, &model_profile);
  assert(model_input.reportable_core_count == 150);
  assert(model_input.ignored_noise_count == 1);
  assert(model_input.reportable_core_source_indices.front() == 0);
  assert(model_input.reportable_core_source_indices.back() == 149);
  assert(model_input.ignored_noise_source_indices.size() == 1);
  assert(model_input.ignored_noise_source_indices[0] == 150);
  assert(model_profile.component_count == 2);
  assert(model_profile.model_obstacle_component_count == 1);
  assert(model_profile.model_noise_component_count == 1);
  assert(model_profile.neighbor_distance_checks < 2000);

  std::vector<float> baseline_v3_points;
  for (int ix = 0; ix < 10; ++ix) {
    for (int iy = 0; iy < 10; ++iy) {
      for (int iz = 0; iz < 10; ++iz) {
        baseline_v3_points.insert(baseline_v3_points.end(), {
            static_cast<float>(-0.2 + ix * 0.05),
            static_cast<float>(-5.2 + iy * 0.05),
            static_cast<float>(0.2 + iz * 0.05)});
      }
    }
  }
  const std::size_t strong_count = baseline_v3_points.size() / 3;
  for (int ix = 0; ix < 2; ++ix) {
    for (int iy = 0; iy < 5; ++iy) {
      for (int iz = 0; iz < 100; ++iz) {
        baseline_v3_points.insert(baseline_v3_points.end(), {
            static_cast<float>(-1.38 + ix * 0.04),
            static_cast<float>(-5.2 + iy * 0.02),
            static_cast<float>(0.1 + iz * 0.016)});
      }
    }
  }
  lidar_mosmetro3d::AnalysisResult baseline_v3_input;
  baseline_v3_input.labels.assign(baseline_v3_points.size() / 3, Zone::kCore);
  baseline_v3_input.core_count = baseline_v3_input.labels.size();
  ApplyBaselineV3(
      baseline_v3_points.data(), baseline_v3_points.size() / 3, baseline_v3_input, 0.25);
  assert(baseline_v3_input.baseline_v3_geometry_obstacle_count == strong_count);
  assert(baseline_v3_input.baseline_v3_boundary_warning_count ==
         baseline_v3_input.core_count - strong_count);
  assert(baseline_v3_input.reportable_core_count == strong_count);
  assert(baseline_v3_input.ignored_noise_count == baseline_v3_input.core_count - strong_count);
  assert(baseline_v3_input.baseline_v3_geometry_obstacle_source_indices.front() == 0);
  assert(baseline_v3_input.baseline_v3_boundary_warning_source_indices.front() == strong_count);

  lidar_mosmetro3d::AnalysisResult baseline_v3_model_input;
  baseline_v3_model_input.labels.assign(model_chain.size() / 3, Zone::kCore);
  baseline_v3_model_input.core_count = baseline_v3_model_input.labels.size();
  ApplyBaselineV3(
      model_chain.data(), model_chain.size() / 3, baseline_v3_model_input, 0.25);
  assert(baseline_v3_model_input.baseline_v3_model_assist_count == 150);
  assert(baseline_v3_model_input.baseline_v3_geometry_obstacle_count == 0);
  assert(baseline_v3_model_input.baseline_v3_boundary_warning_count == 0);
  assert(baseline_v3_model_input.reportable_core_count == 150);

  const auto extended_pairs = ExtendRailPairsForward(pairs, 10.0);
  assert(extended_pairs.size() == pairs.size() + 1);
  assert(std::abs(extended_pairs.back().source_s_m - 10.0) < 1e-9);
  const auto extended_result = AnalyzeCurveEnvelope(raw.data(), raw.size() / 3, extended_pairs, core, expanded);
  assert(extended_result.labels[4] == Zone::kCore);
  assert(extended_result.core_count == 2 && extended_result.unknown_count == 1);

  // The tangent is derived from the pair centres.  The final observed gauge
  // must move as one rigid cross-section even if the two final rail samples
  // have different local slopes due to measurement noise.
  const std::vector<RailPair> noisy_tail_pairs{
      {20.0, {-1.0F, -20.0F, 0.0F}, {1.0F, -20.0F, 0.0F}},
      {22.0, {-1.2F, -22.0F, 0.0F}, {0.8F, -21.5F, 0.0F}},
  };
  const auto rigid_tangent = ExtendRailPairsForward(noisy_tail_pairs, 30.0);
  const auto& observed_tail = noisy_tail_pairs.back();
  const auto& rigid_tail = rigid_tangent.back();
  assert(std::abs((rigid_tail.right.x - rigid_tail.left.x) -
                  (observed_tail.right.x - observed_tail.left.x)) < 1e-6);
  assert(std::abs((rigid_tail.right.y - rigid_tail.left.y) -
                  (observed_tail.right.y - observed_tail.left.y)) < 1e-6);
  assert(std::abs((rigid_tail.right.z - rigid_tail.left.z) -
                  (observed_tail.right.z - observed_tail.left.z)) < 1e-6);

  const std::vector<RailPair> arc_pairs{
      {4.0, {-1.0F, -10.0F, 0.0F}, {1.0F, -10.0F, 0.0F}},
      {6.0, {0.986693F, -9.800666F, 0.1F}, {2.986693F, -9.800666F, 0.1F}},
      {8.0, {2.894183F, -9.210610F, 0.2F}, {4.894183F, -9.210610F, 0.2F}},
  };
  const auto arc_extension = ExtendRailPairsForwardArcLimited(arc_pairs, 4.0, 80.0);
  assert(arc_extension.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kApplied);
  assert(arc_extension.rail_pairs.size() == arc_pairs.size() + 2);
  assert(std::abs(arc_extension.applied_horizon_m - 4.0) < 1e-9);
  assert(std::abs(arc_extension.sample_step_m - 2.0) < 1e-9);
  const auto& arc_end = arc_extension.rail_pairs.back();
  assert(std::abs(arc_end.source_s_m - 12.0) < 1e-9);
  assert(std::abs((arc_end.left.x + arc_end.right.x) * .5 - 7.173561F) < 1e-3);
  assert(std::abs((arc_end.left.y + arc_end.right.y) * .5 + 6.967067F) < 1e-3);
  const auto capped_arc = ExtendRailPairsForwardArcLimited(arc_pairs, 20.0, 9.0);
  assert(capped_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kApplied);
  assert(std::abs(capped_arc.applied_horizon_m - 1.0) < 1e-9);
  assert(std::abs(capped_arc.rail_pairs.back().source_s_m - 9.0) < 1e-9);
  const auto clamped_turn_arc = ExtendRailPairsForwardArcClamped(arc_pairs, 20.0, 80.0, 3.0, 15.0);
  assert(clamped_turn_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kClampedToMaxTurn);
  assert(clamped_turn_arc.applied_turn_deg <= 15.0 + 1e-6);
  assert(clamped_turn_arc.applied_horizon_m < 20.0);
  const auto rejected_arc = ExtendRailPairsForwardArcClamped(arc_pairs, 4.0, 80.0, 100.0, 15.0);
  // A rejected arc must not silently use the tangent algorithm.  Only the
  // observed geometry remains, so points beyond it stay UNKNOWN.
  assert(rejected_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kClampedRejected);
  assert(rejected_arc.rail_pairs.size() == arc_pairs.size());
  const std::vector<RailPair> gentle_arc_pairs{
      {3.0, {-0.785F, -3.000F, 0.0F}, {0.815F, -3.000F, 0.0F}},
      {7.0, {-0.718F, -6.999F, 0.0F}, {0.882F, -6.999F, 0.0F}},
      {11.0, {-0.598F, -10.998F, 0.0F}, {1.002F, -10.998F, 0.0F}},
      {15.0, {-0.425F, -14.994F, 0.0F}, {1.175F, -14.994F, 0.0F}},
      {19.0, {-0.199F, -18.987F, 0.0F}, {1.401F, -18.987F, 0.0F}},
      {23.0, {0.081F, -22.978F, 0.0F}, {1.681F, -22.978F, 0.0F}},
      {27.0, {0.414F, -26.964F, 0.0F}, {2.014F, -26.964F, 0.0F}},
  };
  const auto gentle_arc = ExtendRailPairsForwardArcClamped(
      gentle_arc_pairs, 53.0, 80.0, 100.0, 15.0, 7);
  assert(gentle_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kClampedApplied);
  assert(std::abs(gentle_arc.rail_pairs.back().source_s_m - 80.0) < 1e-9);
  const auto& gentle_observed_tail = gentle_arc_pairs.back();
  const auto& gentle_synthetic_tail = gentle_arc.rail_pairs.back();
  assert(std::abs(std::hypot(gentle_synthetic_tail.right.x - gentle_synthetic_tail.left.x,
                             gentle_synthetic_tail.right.y - gentle_synthetic_tail.left.y) -
                  std::hypot(gentle_observed_tail.right.x - gentle_observed_tail.left.x,
                             gentle_observed_tail.right.y - gentle_observed_tail.left.y)) < 1e-5);
  const std::vector<RailPair> window_arc_pairs{
      {0.0, {-1.0F, 0.0F, 0.0F}, {1.0F, 0.0F, 0.0F}},
      {10.0, {0.0F, -10.0F, 0.0F}, {2.0F, -10.0F, 0.0F}},
      {20.0, {1.0F, -20.0F, 0.0F}, {3.0F, -20.0F, 0.0F}},
      {30.0, {1.0F, -30.0F, 0.0F}, {3.0F, -30.0F, 0.0F}},
      {40.0, {1.0F, -40.0F, 0.0F}, {3.0F, -40.0F, 0.0F}},
  };
  const auto smoothed_arc = ExtendRailPairsForwardArcClamped(window_arc_pairs, 5.0, 80.0, 1.0, 8.0, 5);
  assert(smoothed_arc.fit_window_pairs == 5);
  assert(std::isfinite(smoothed_arc.estimated_radius_m));
  assert(smoothed_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kClampedApplied ||
         smoothed_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kClampedToMaxTurn);
  const auto disabled_arc = ExtendRailPairsForwardArcLimited(arc_pairs, 0.0, 80.0);
  assert(disabled_arc.rail_pairs.size() == arc_pairs.size());
  assert(disabled_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kHorizonDisabled);
  const std::vector<RailPair> collinear_pairs{
      {4.0, {-1.0F, -4.0F, 0.0F}, {1.0F, -4.0F, 0.0F}},
      {6.0, {-1.0F, -6.0F, 0.0F}, {1.0F, -6.0F, 0.0F}},
      {8.0, {-1.0F, -8.0F, 0.0F}, {1.0F, -8.0F, 0.0F}},
  };
  const auto collinear_arc = ExtendRailPairsForwardArcLimited(collinear_pairs, 4.0, 80.0);
  assert(collinear_arc.rail_pairs.size() == collinear_pairs.size());
  assert(collinear_arc.status == lidar_mosmetro3d::ArcLimitedExtensionStatus::kCollinearObservedCenters);

  const std::vector<RailPair> skewed_pairs{
      {0.0, {-1.0F, 0.0F, 0.0F}, {1.0F, 0.0F, 0.0F}},
      {2.0, {-0.5F, -2.0F, 0.0F}, {1.5F, -2.0F, 0.0F}},
  };
  const auto core_wireframe = BuildCurveEnvelopeWireframe(skewed_pairs, core);
  const auto expanded_wireframe = BuildCurveEnvelopeWireframe(skewed_pairs, expanded);
  assert(core_wireframe.size() == 12 && expanded_wireframe.size() == 12);
  const double dx = 0.5, dy = -2.0, length = std::hypot(dx, dy);
  const double expected_nx = dy / length, expected_ny = -dx / length;
  const auto& lateral_edge = core_wireframe[1];
  const double edge_x = static_cast<double>(lateral_edge.end.x) - lateral_edge.start.x;
  const double edge_y = static_cast<double>(lateral_edge.end.y) - lateral_edge.start.y;
  assert(std::abs(edge_x * expected_ny - edge_y * expected_nx) < 1e-6);
  const std::vector<float> boundary_point{
      lateral_edge.start.x, lateral_edge.start.y, lateral_edge.start.z};
  const auto boundary_result = AnalyzeCurveEnvelope(
      boundary_point.data(), 1, skewed_pairs, core, expanded);
  assert(boundary_result.labels[0] == Zone::kCore);

  const auto unavailable = AnalyzeCurveEnvelope(raw.data(), raw.size() / 3, {}, core, expanded);
  assert(unavailable.unknown_count == raw.size() / 3 && unavailable.core_count == 0);
  assert(BuildCurveEnvelopeWireframe({}, core).empty());

  bool invalid_pair_rejected = false;
  try {
    AnalyzeCurveEnvelope(raw.data(), raw.size() / 3, {pairs.front()}, core, expanded);
  } catch (const std::invalid_argument&) {
    invalid_pair_rejected = true;
  }
  assert(invalid_pair_rejected);
}
