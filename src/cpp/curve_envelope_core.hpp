#pragma once

#include <cstddef>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

namespace lidar_mosmetro3d {

enum class Zone : std::uint8_t {
  kUnknown = 0,
  kCore = 1,
  kMargin = 2,
  kOutsideReference = 3,
};

struct Point3f {
  float x;
  float y;
  float z;
};

struct RailPair {
  double source_s_m;
  Point3f left;
  Point3f right;
};

enum class ArcLimitedExtensionStatus : std::uint8_t {
  kApplied = 0,
  kHorizonDisabled = 1,
  kAtForwardLimit = 2,
  kInsufficientObservedPairs = 3,
  kCollinearObservedCenters = 4,
  kClampedApplied = 5,
  kClampedToMaxTurn = 6,
  kClampedRejected = 7,
};

struct ArcLimitedExtensionResult {
  std::vector<RailPair> rail_pairs;
  ArcLimitedExtensionStatus status = ArcLimitedExtensionStatus::kHorizonDisabled;
  double applied_horizon_m = 0.0;
  double sample_step_m = 0.0;
  double estimated_radius_m = std::numeric_limits<double>::quiet_NaN();
  double requested_turn_deg = 0.0;
  double applied_turn_deg = 0.0;
  std::size_t fit_window_pairs = 0;
};

struct Bounds {
  double left;
  double right;
  double bottom;
  double top;
};

struct LineSegment3f {
  Point3f start;
  Point3f end;
};

struct NearestPoint {
  std::size_t source_index = std::numeric_limits<std::size_t>::max();
  double distance_from_source_origin_m = std::numeric_limits<double>::infinity();
};

struct CoreNoiseFilterConfig {
  std::size_t min_reportable_core_points = 22;
  double connectivity_radius_m = 0.25;
  double max_axis_span_m = 1.0;
  double max_average_axis_distance_m = 1.20;
  bool enabled = true;
};

struct AnalysisResult {
  std::vector<Zone> labels;
  std::size_t core_count = 0;
  std::size_t reportable_core_count = 0;
  std::size_t ignored_noise_count = 0;
  std::size_t baseline_v3_geometry_obstacle_count = 0;
  std::size_t baseline_v3_boundary_warning_count = 0;
  std::size_t baseline_v3_model_assist_count = 0;
  std::size_t baseline_v3_early_candidate_count = 0;
  std::size_t margin_count = 0;
  std::size_t outside_reference_count = 0;
  std::size_t unknown_count = 0;
  std::vector<std::size_t> reportable_core_source_indices;
  std::vector<std::size_t> ignored_noise_source_indices;
  std::vector<std::size_t> baseline_v3_geometry_obstacle_source_indices;
  std::vector<std::size_t> baseline_v3_boundary_warning_source_indices;
  std::vector<std::size_t> baseline_v3_model_assist_source_indices;
  std::vector<std::size_t> baseline_v3_early_candidate_source_indices;
  NearestPoint nearest_core;
  NearestPoint nearest_reportable_core;
  NearestPoint nearest_baseline_v3_early_candidate;
  NearestPoint nearest_margin;
};

struct BaselineV3ComponentProfile {
  std::size_t point_count = 0;
  double nearest_source_origin_m = 0.0;
  double min_x = 0.0, max_x = 0.0;
  double min_y = 0.0, max_y = 0.0;
  double min_z = 0.0, max_z = 0.0;
  double assist_score = -1.0;
  std::string decision;
};

struct FrozenNoiseTreeV1Profile {
  std::size_t core_index_count = 0;
  std::size_t component_count = 0;
  std::size_t model_obstacle_component_count = 0;
  std::size_t model_noise_component_count = 0;
  std::uint64_t neighbor_distance_checks = 0;
  double core_index_extract_ms = 0.0;
  double connected_components_and_features_ms = 0.0;
  double tree_decision_ms = 0.0;
  double output_finalize_ms = 0.0;
  std::vector<BaselineV3ComponentProfile> baseline_v3_components;
};

// Builds one segment per adjacent pair. Pairs must describe one contiguous run.
// This function never extrapolates before the first or after the last pair.
std::vector<RailPair> ValidateRailPairs(const std::vector<RailPair>& pairs);

// Extends the final observed pair along the last local tangent up to
// `target_source_s_m`. The inserted pair is synthetic; callers must expose that
// distinction when serializing diagnostics.
std::vector<RailPair> ExtendRailPairsForward(const std::vector<RailPair>& pairs,
                                             double target_source_s_m);

// Experimental candidate: extends the final observed rail-pair geometry along
// the circle through the last three pair centres. The generated points are
// synthetic and limited to min(requested_horizon_m, max_source_s_m - last_s).
// It never falls back to a tangent: unavailable arc support returns the
// original observed pairs with an explicit status.
ArcLimitedExtensionResult ExtendRailPairsForwardArcLimited(
    const std::vector<RailPair>& pairs, double requested_horizon_m,
    double max_source_s_m);

// Safer experimental variant for noisy rail tails. It fits a centre arc over
// the final window, caps the generated arc to `max_turn_deg`, and returns only
// observed pairs with kClampedRejected when that arc is not acceptable.
ArcLimitedExtensionResult ExtendRailPairsForwardArcClamped(
    const std::vector<RailPair>& pairs, double requested_horizon_m,
    double max_source_s_m, double min_radius_m, double max_turn_deg,
    std::size_t fit_window_pairs = 5);

const char* ArcLimitedExtensionStatusName(ArcLimitedExtensionStatus status);

// `xyz` contains raw X,Y,Z triplets in source coordinates and is not modified.
// For an empty segment list every finite point is UNKNOWN. An invalid triplet
// length or non-finite source value throws std::invalid_argument.
AnalysisResult AnalyzeCurveEnvelope(const float* xyz, std::size_t point_count,
                                    const std::vector<RailPair>& pairs,
                                    const Bounds& core, const Bounds& expanded,
                                    const CoreNoiseFilterConfig& noise_config = {});

// Splits CORE returns into reportable connected components and sparse noise.
// Raw CORE labels/counts remain unchanged; only reportable_* and ignored_noise_*
// fields are updated. Components smaller than min_reportable_core_points or
// too elongated/far from the rail axis are ignored everywhere in the envelope.
void ApplyCoreNoiseFilter(const float* xyz, std::size_t point_count,
                          AnalysisResult& result,
                          const std::vector<RailPair>& pairs = {},
                          const CoreNoiseFilterConfig& config = {});

// Applies the current forest-lite baseline_v3_assist_score.  The raw CORE
// labels/counts remain unchanged; only reportable_*, ignored_noise_* and
// nearest_reportable_core are updated.
void ApplyBaselineV3AssistScore(const float* xyz, std::size_t point_count,
                              AnalysisResult& result,
                              double connectivity_radius_m = 0.25,
                              FrozenNoiseTreeV1Profile* profile = nullptr);

void ApplyBaselineV3(const float* xyz, std::size_t point_count,
                     AnalysisResult& result,
                     double connectivity_radius_m = 0.25,
                     FrozenNoiseTreeV1Profile* profile = nullptr);

// Returns the twelve edges of each finite segment prism in source coordinates.
// The prism basis is shared with AnalyzeCurveEnvelope; the viewer must draw
// these lines instead of reconstructing envelope geometry from rail pairs.
std::vector<LineSegment3f> BuildCurveEnvelopeWireframe(
    const std::vector<RailPair>& pairs, const Bounds& bounds);

std::string ZoneName(Zone zone);

}  // namespace lidar_mosmetro3d
