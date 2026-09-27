#pragma once

#include "curve_envelope_core.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace lidar_mosmetro3d {

// `kDevelopmentCandidate` is intentionally opt-in. Both modes consume the
// same station-local observed rail-pair candidates; neither extrapolates.
enum class RailSelectionMethod {
  kBaseline,
  kDevelopmentCandidate,
};

const char* RailSelectionMethodName(RailSelectionMethod method);

// Values must be supplied by the runtime from the same configuration that is
// used for validation. The defaults intentionally mirror the current new_data
// experimental configuration and are not a calibrated train contract.
struct AutoRailsConfig {
  double forward_min = 2.0;
  double forward_max = 80.0;
  double station_length = 2.0;
  double lateral_min = -4.0;
  double lateral_max = 4.0;
  double cell_width = 0.04;
  int min_cell_points = 2;
  double floor_quantile = 0.2;
  double cell_floor_quantile = 0.1;
  double floor_band_below = 0.35;
  double floor_band_above = 0.7;
  double head_quantile = 0.9;
  double head_band = 0.025;
  double flank_min = 0.12;
  double flank_max = 0.32;
  int min_flank_cells = 2;
  double min_prominence = 0.065;
  double max_prominence = 0.4;
  double peak_separation = 0.22;
  double pair_min = 1.4;
  double pair_max = 1.8;
  double max_cross_height = 0.25;
  int min_stations = 6;
  double min_span = 10.0;
  double max_gap = 6.0;
  double min_coverage = 0.65;
  double max_slope = 0.12;
  double lateral_tolerance = 0.1;
  double height_tolerance = 0.1;
  double max_rms = 0.055;
  double ambiguity_ratio = 0.85;
  int max_pairs_per_station = 8;
  int max_seed_pairs = 10000;
};

struct AutoRailsResult {
  std::string status = "UNKNOWN";
  std::string reason;
  std::vector<RailPair> rail_pairs;
  int station_count = 0;
  int pair_stations = 0;
  int supported_stations = 0;
  double rms = 0.0;
  int best_path_score = 0;
  double best_path_cost = 0.0;
  double best_path_span_m = 0.0;
  double best_path_coverage = 0.0;
  double best_path_start_s_m = 0.0;
  double best_path_end_s_m = 0.0;
  int competing_path_score = 0;
  double competing_path_cost = 0.0;
  double competing_path_lateral_displacement_m = 0.0;
  double competing_path_end_s_m = 0.0;
  std::vector<RailPair> best_path_pairs;
  std::vector<RailPair> competing_path_pairs;
};

AutoRailsResult DetectAutoRails(const float* xyz, std::size_t point_count,
                                const AutoRailsConfig& config = {},
                                RailSelectionMethod method = RailSelectionMethod::kDevelopmentCandidate);

}  // namespace lidar_mosmetro3d
