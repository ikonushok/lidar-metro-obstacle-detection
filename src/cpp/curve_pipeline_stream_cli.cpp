#include "auto_rails_core.hpp"
#include "curve_envelope_core.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

void AppendWireframeJson(
    std::ostringstream& json,
    const std::vector<lidar_mosmetro3d::LineSegment3f>& wireframe) {
  json << '[';
  for (std::size_t index = 0; index < wireframe.size(); ++index) {
    if (index) json << ',';
    const auto& line = wireframe[index];
    json << "[[" << line.start.x << ',' << line.start.y << ',' << line.start.z
         << "],[" << line.end.x << ',' << line.end.y << ',' << line.end.z << "]]";
  }
  json << ']';
}

void AppendRailPairsJson(
    std::ostringstream& json,
    const std::vector<lidar_mosmetro3d::RailPair>& rail_pairs) {
  json << '[';
  for (std::size_t index = 0; index < rail_pairs.size(); ++index) {
    if (index) json << ',';
    const auto& pair = rail_pairs[index];
    json << "{\"source_s_m\":" << pair.source_s_m << ",\"left_xyz\":["
         << pair.left.x << ',' << pair.left.y << ',' << pair.left.z
         << "],\"right_xyz\":[" << pair.right.x << ',' << pair.right.y << ','
         << pair.right.z << "]}";
  }
  json << ']';
}

void AppendModelFilterProfileJson(
    std::ostringstream& json,
    const lidar_mosmetro3d::FrozenNoiseTreeV1Profile& profile) {
  json << "\"model_profile_core_index_count\":" << profile.core_index_count
       << ",\"model_profile_component_count\":" << profile.component_count
       << ",\"model_profile_obstacle_component_count\":" << profile.model_obstacle_component_count
       << ",\"model_profile_noise_component_count\":" << profile.model_noise_component_count
       << ",\"model_profile_neighbor_distance_checks\":" << profile.neighbor_distance_checks
       << ",\"model_profile_core_index_extract_ms\":" << profile.core_index_extract_ms
       << ",\"model_profile_connected_components_and_features_ms\":"
       << profile.connected_components_and_features_ms
       << ",\"model_profile_tree_decision_ms\":" << profile.tree_decision_ms
       << ",\"model_profile_output_finalize_ms\":" << profile.output_finalize_ms;
}

void AppendAutoRailsFailureDiagnosticsJson(
    std::ostringstream& json,
    const lidar_mosmetro3d::AutoRailsResult& rails) {
  json << "\"rail_axis_failure_diagnostics\":{"
       << "\"station_count\":" << rails.station_count
       << ",\"pair_stations\":" << rails.pair_stations
       << ",\"supported_stations\":" << rails.supported_stations
       << ",\"best_path_score\":" << rails.best_path_score
       << ",\"best_path_cost\":" << rails.best_path_cost
       << ",\"best_path_span_m\":" << rails.best_path_span_m
       << ",\"best_path_coverage\":" << rails.best_path_coverage
       << ",\"best_path_start_s_m\":" << rails.best_path_start_s_m
       << ",\"best_path_end_s_m\":" << rails.best_path_end_s_m
       << ",\"competing_path_score\":" << rails.competing_path_score
       << ",\"competing_path_cost\":" << rails.competing_path_cost
       << ",\"competing_path_lateral_displacement_m\":"
       << rails.competing_path_lateral_displacement_m
       << ",\"competing_path_end_s_m\":" << rails.competing_path_end_s_m
       << ",\"best_path_pairs_source_xyz\":";
  AppendRailPairsJson(json, rails.best_path_pairs);
  json << ",\"competing_path_pairs_source_xyz\":";
  AppendRailPairsJson(json, rails.competing_path_pairs);
  json << "}";
}

std::string UnknownJson(
    const lidar_mosmetro3d::AutoRailsResult& rails,
    const lidar_mosmetro3d::AutoRailsConfig& config,
    std::uint64_t point_count, const std::string& forward_extension_method,
    double arc_extension_horizon_m, double min_arc_radius_m, double max_arc_turn_deg,
    std::size_t arc_fit_window_pairs, bool lean_benchmark, bool use_model_filter) {
  std::ostringstream json;
  json << std::fixed << std::setprecision(6)
        << "{\"format\":\""
        << (lean_benchmark ? "lidar-curve-envelope-lean-benchmark-v1" : "lidar-curve-envelope-v1")
        << "\",\"status\":\"UNKNOWN\",\"system_status\":\"UNKNOWN\","
        << "\"curve_axis_status\":\"MISSING_CURVE_AXIS\",\"reason\":\"" << rails.reason << "\","
       << "\"safety_decision_permitted\":false,\"intrusion_candidate_present\":null,"
       << "\"reportable_intrusion_candidate_present\":null,\"raw_core_return_present\":null,"
       << "\"all_core_returns_are_intrusion_candidates\":false,\"margin_return_present\":null,"
       << "\"compute_backend_requested\":\"direct_cpu_stream\",\"compute_backend_used\":\"cpu\","
       << "\"rail_selection_method\":\"development_candidate\","
       << "\"forward_extension_method\":\"" << forward_extension_method << "\","
       << "\"arc_extension_horizon_m\":" << arc_extension_horizon_m << ","
       << "\"min_arc_radius_m\":" << min_arc_radius_m << ","
       << "\"max_arc_turn_deg\":" << max_arc_turn_deg << ","
       << "\"arc_fit_window_pairs\":" << arc_fit_window_pairs << ","
       << "\"forward_extension_status\":\"NOT_EVALUATED\","
       << "\"rail_search_config\":{\"forward_min_m\":" << config.forward_min
       << ",\"forward_max_m\":" << config.forward_max
       << ",\"station_length_m\":" << config.station_length
       << ",\"cell_width_m\":" << config.cell_width << "},"
        << "\"point_count\":" << point_count << ",\"rail_pair_count\":0,"
        << "\"noise_filter_mode\":\"" << (use_model_filter ? "candidate_baseline_v2" : "legacy") << "\",";
  AppendAutoRailsFailureDiagnosticsJson(json, rails);
  if (lean_benchmark) {
    json << ",\"processing_ms\":0.000000}";
    return json.str();
  }
  json << ','
       << "\"curve_axis_polyline_source_xyz\":[],\"rail_pairs_source_xyz\":[],"
       << "\"core_bounds_source_axis\":null,\"expanded_bounds_source_axis\":null,"
       << "\"core_envelope_wireframe_source_xyz\":[],\"expanded_envelope_wireframe_source_xyz\":[],"
       << "\"core_source_indices\":[],\"reportable_core_source_indices\":[],"
       << "\"ignored_noise_source_indices\":[],\"margin_source_indices\":[]}";
  return json.str();
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 2 || argc > 12) {
    std::cerr << "usage: curve_pipeline_stream_cli RAIL_FORWARD_MIN_M "
                 "[--observed-only | --arc-limited HORIZON_M | "
                 "--arc-clamped HORIZON_M MIN_RADIUS_M MAX_TURN_DEG] "
                 "[--arc-fit-window N] [--lean-model-benchmark] [--use-model-filter] "
                 "[--compare-noise-filters] [--profile-model-filter]\n";
    return 2;
  }
  try {
    lidar_mosmetro3d::AutoRailsConfig config;
    config.forward_min = std::stod(argv[1]);
    bool observed_only = false;
    bool arc_limited = false;
    bool arc_clamped = false;
    bool lean_benchmark = false;
    bool use_model_filter = false;
    bool compare_noise_filters = false;
    bool profile_model_filter = false;
    double arc_extension_horizon_m = 0.0;
    double min_arc_radius_m = 60.0;
    double max_arc_turn_deg = 8.0;
    std::size_t arc_fit_window_pairs = 5;
    for (int arg = 2; arg < argc; ++arg) {
      const std::string option = argv[arg];
      if (option == "--observed-only") {
        if (observed_only || arc_limited || arc_clamped) throw std::runtime_error("duplicate stream mode");
        observed_only = true;
      } else if (option == "--arc-limited") {
        if (observed_only || arc_limited || arc_clamped || arg + 1 >= argc) throw std::runtime_error("invalid arc limited mode");
        arc_limited = true;
        arc_extension_horizon_m = std::stod(argv[++arg]);
      } else if (option == "--arc-clamped") {
        if (observed_only || arc_limited || arc_clamped || arg + 3 >= argc) throw std::runtime_error("invalid arc clamped mode");
        arc_clamped = true;
        arc_extension_horizon_m = std::stod(argv[++arg]);
        min_arc_radius_m = std::stod(argv[++arg]);
        max_arc_turn_deg = std::stod(argv[++arg]);
      } else if (option == "--lean-model-benchmark") {
        if (lean_benchmark) throw std::runtime_error("duplicate lean benchmark mode");
        lean_benchmark = true;
      } else if (option == "--use-model-filter") {
        if (use_model_filter) throw std::runtime_error("duplicate model filter mode");
        use_model_filter = true;
      } else if (option == "--compare-noise-filters") {
        if (compare_noise_filters) throw std::runtime_error("duplicate compare noise filters mode");
        compare_noise_filters = true;
      } else if (option == "--profile-model-filter") {
        if (profile_model_filter) throw std::runtime_error("duplicate profile model filter mode");
        profile_model_filter = true;
      } else if (option == "--arc-fit-window") {
        if (arg + 1 >= argc) throw std::runtime_error("invalid arc fit window");
        const auto parsed = std::stoul(argv[++arg]);
        if (parsed < 3) throw std::runtime_error("invalid arc fit window");
        arc_fit_window_pairs = static_cast<std::size_t>(parsed);
      } else {
        throw std::runtime_error("invalid stream mode");
      }
    }
    if (!std::isfinite(arc_extension_horizon_m) || arc_extension_horizon_m < 0.0)
      throw std::runtime_error("invalid arc extension horizon");
    if (!std::isfinite(min_arc_radius_m) || min_arc_radius_m <= 0.0 ||
        !std::isfinite(max_arc_turn_deg) || max_arc_turn_deg <= 0.0)
      throw std::runtime_error("invalid arc clamp parameters");
    const lidar_mosmetro3d::Bounds core{-1.4, 1.4, 0.0, 3.7};
    const lidar_mosmetro3d::Bounds expanded{-1.9, 1.9, -0.5, 4.2};
    const lidar_mosmetro3d::CoreNoiseFilterConfig noise_config{};
    lidar_mosmetro3d::CoreNoiseFilterConfig raw_core_config{};
    raw_core_config.enabled = false;
    const bool active_model_filter = use_model_filter || lean_benchmark;
    const std::string requested_forward_extension_method = observed_only ? "observed_only"
        : arc_limited ? "arc_limited" : arc_clamped ? "arc_clamped" : "tangent";
    while (true) {
      std::uint64_t point_count = 0;
      std::cin.read(reinterpret_cast<char*>(&point_count), sizeof(point_count));
      if (std::cin.gcount() == 0 && std::cin.eof()) break;
      if (std::cin.gcount() != static_cast<std::streamsize>(sizeof(point_count)) ||
          point_count == 0 || point_count > 10'000'000) {
        throw std::runtime_error("invalid streamed point count");
      }
      std::vector<float> xyz(static_cast<std::size_t>(point_count) * 3);
      std::cin.read(reinterpret_cast<char*>(xyz.data()),
                    static_cast<std::streamsize>(xyz.size() * sizeof(float)));
      if (!std::cin) throw std::runtime_error("truncated streamed XYZ frame");
      if (!std::all_of(xyz.begin(), xyz.end(), [](float value) { return std::isfinite(value); })) {
        throw std::runtime_error("nonfinite streamed XYZ frame");
      }
      const auto started = std::chrono::steady_clock::now();
      const auto rails = lidar_mosmetro3d::DetectAutoRails(
          xyz.data(), point_count, config, lidar_mosmetro3d::RailSelectionMethod::kDevelopmentCandidate);
      if (rails.rail_pairs.size() < 2) {
        std::cout << UnknownJson(rails, config, point_count,
                                 requested_forward_extension_method,
                                 arc_extension_horizon_m, min_arc_radius_m, max_arc_turn_deg,
                                 arc_fit_window_pairs, lean_benchmark, active_model_filter)
                  << "\n" << std::flush;
        continue;
      }
      std::vector<lidar_mosmetro3d::RailPair> active_pairs;
      std::string forward_extension_method = "tangent";
      std::string forward_extension_status;
      double forward_extension_horizon_m = 0.0;
      double forward_extension_sample_step_m = 0.0;
      double arc_estimated_radius_m = std::numeric_limits<double>::quiet_NaN();
      double arc_requested_turn_deg = 0.0;
      double arc_applied_turn_deg = 0.0;
      std::size_t arc_fit_window_pairs_used = 0;
      if (observed_only) {
        active_pairs = rails.rail_pairs;
        forward_extension_method = "observed_only";
        forward_extension_status = "OBSERVED_ONLY";
      } else if (arc_limited) {
        const auto arc_extension = lidar_mosmetro3d::ExtendRailPairsForwardArcLimited(
            rails.rail_pairs, arc_extension_horizon_m, config.forward_max);
        active_pairs = arc_extension.rail_pairs;
        forward_extension_method = "arc_limited";
        forward_extension_status = lidar_mosmetro3d::ArcLimitedExtensionStatusName(arc_extension.status);
        forward_extension_horizon_m = arc_extension.applied_horizon_m;
        forward_extension_sample_step_m = arc_extension.sample_step_m;
        arc_estimated_radius_m = arc_extension.estimated_radius_m;
        arc_requested_turn_deg = arc_extension.requested_turn_deg;
        arc_applied_turn_deg = arc_extension.applied_turn_deg;
        arc_fit_window_pairs_used = arc_extension.fit_window_pairs;
      } else if (arc_clamped) {
        const auto arc_extension = lidar_mosmetro3d::ExtendRailPairsForwardArcClamped(
            rails.rail_pairs, arc_extension_horizon_m, config.forward_max,
            min_arc_radius_m, max_arc_turn_deg, arc_fit_window_pairs);
        active_pairs = arc_extension.rail_pairs;
        forward_extension_method = "arc_clamped";
        forward_extension_status = lidar_mosmetro3d::ArcLimitedExtensionStatusName(arc_extension.status);
        forward_extension_horizon_m = arc_extension.applied_horizon_m;
        forward_extension_sample_step_m = arc_extension.sample_step_m;
        arc_estimated_radius_m = arc_extension.estimated_radius_m;
        arc_requested_turn_deg = arc_extension.requested_turn_deg;
        arc_applied_turn_deg = arc_extension.applied_turn_deg;
        arc_fit_window_pairs_used = arc_extension.fit_window_pairs;
      } else {
        active_pairs = lidar_mosmetro3d::ExtendRailPairsForward(
            rails.rail_pairs, config.forward_max);
        forward_extension_status = active_pairs.size() > rails.rail_pairs.size()
            ? "TANGENT_APPLIED" : "AT_FORWARD_LIMIT";
        forward_extension_horizon_m = active_pairs.back().source_s_m - rails.rail_pairs.back().source_s_m;
      }
      auto raw_result = lidar_mosmetro3d::AnalyzeCurveEnvelope(
          xyz.data(), point_count, active_pairs, core, expanded, raw_core_config);
      const double common_processing_ms = std::chrono::duration<double, std::milli>(
          std::chrono::steady_clock::now() - started).count();
      auto legacy_result = raw_result;
      auto model_result = raw_result;
      bool legacy_filter_computed = false;
      bool model_filter_computed = false;
      double legacy_filter_ms = 0.0;
      double model_filter_ms = 0.0;
      lidar_mosmetro3d::FrozenNoiseTreeV1Profile model_filter_profile;
      if (!active_model_filter || compare_noise_filters) {
        auto legacy_filter_started = std::chrono::steady_clock::now();
        lidar_mosmetro3d::ApplyCoreNoiseFilter(
            xyz.data(), point_count, legacy_result, active_pairs, noise_config);
        legacy_filter_ms = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - legacy_filter_started).count();
        legacy_filter_computed = true;
      }
      if (active_model_filter || compare_noise_filters) {
        auto model_filter_started = std::chrono::steady_clock::now();
        lidar_mosmetro3d::ApplyCandidateBaselineV2(
            xyz.data(), point_count, model_result, noise_config.connectivity_radius_m,
            profile_model_filter ? &model_filter_profile : nullptr);
        model_filter_ms = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - model_filter_started).count();
        model_filter_computed = true;
      }
      const auto& result = active_model_filter ? model_result : legacy_result;
      const bool raw_core = result.core_count > 0;
      const bool intrusion = result.reportable_core_count > 0;
      const bool margin = result.margin_count > 0;
      if (lean_benchmark) {
        const bool model_intrusion = model_result.reportable_core_count > 0;
        const char* model_status = model_intrusion ? "OBSERVED_CORE_INTRUSION_CANDIDATE"
                                  : raw_core ? "NO_REPORTABLE_INTRUSION_NOISE_IGNORED"
                                  : margin ? "OBSERVED_MARGIN_RETURN" : "UNKNOWN";
        const double lean_processing_ms = common_processing_ms + model_filter_ms;
        std::ostringstream lean_json;
        lean_json << std::fixed << std::setprecision(6)
                  << "{\"format\":\"lidar-curve-envelope-lean-benchmark-v1\","
                  << "\"status\":\"" << model_status << "\","
                  << "\"system_status\":\"UNKNOWN\","
                  << "\"curve_axis_status\":\"CURVE_AXIS_SUPPORTED\","
                  << "\"safety_decision_permitted\":false,"
                  << "\"rail_selection_method\":\"development_candidate\","
                  << "\"forward_extension_method\":\"" << forward_extension_method << "\","
                  << "\"obstacle_candidate_present\":" << (model_intrusion ? "true" : "false") << ','
                  << "\"raw_core_return_present\":" << (raw_core ? "true" : "false") << ','
                  << "\"margin_return_present\":" << (margin ? "true" : "false") << ','
                  << "\"point_count\":" << point_count << ','
                  << "\"rail_pair_count\":" << active_pairs.size() << ','
                  << "\"observed_rail_pair_count\":" << rails.rail_pairs.size() << ','
                  << "\"core_count\":" << raw_result.core_count << ','
                  << "\"model_reportable_core_count\":" << model_result.reportable_core_count << ','
                  << "\"model_ignored_noise_count\":" << model_result.ignored_noise_count << ','
                  << "\"margin_count\":" << raw_result.margin_count << ','
                  << "\"outside_reference_count\":" << raw_result.outside_reference_count << ','
                  << "\"unknown_count\":" << raw_result.unknown_count << ','
                  << "\"processing_ms\":" << lean_processing_ms << ','
                  << "\"common_processing_ms\":" << common_processing_ms << ','
                  << "\"arc_extension_horizon_m\":" << arc_extension_horizon_m << ','
                  << "\"min_arc_radius_m\":" << min_arc_radius_m << ','
                  << "\"max_arc_turn_deg\":" << max_arc_turn_deg << ','
                  << "\"arc_fit_window_pairs\":" << arc_fit_window_pairs << ','
                  << "\"arc_fit_window_pairs_used\":" << arc_fit_window_pairs_used << ','
                  << "\"model_noise_filter_ms\":" << model_filter_ms << ','
                  << "\"model_noise_filter_name\":\"candidate_baseline_v2\"";
        if (profile_model_filter) {
          lean_json << ',';
          AppendModelFilterProfileJson(lean_json, model_filter_profile);
        }
        lean_json << '}';
        std::cout << lean_json.str() << "\n" << std::flush;
        continue;
      }
      const auto wireframe_started = std::chrono::steady_clock::now();
      const auto core_wireframe = lidar_mosmetro3d::BuildCurveEnvelopeWireframe(active_pairs, core);
      const auto expanded_wireframe = lidar_mosmetro3d::BuildCurveEnvelopeWireframe(active_pairs, expanded);
      const double wireframe_ms = std::chrono::duration<double, std::milli>(
          std::chrono::steady_clock::now() - wireframe_started).count();
      const double legacy_processing_ms = common_processing_ms + legacy_filter_ms + wireframe_ms;
      const double model_processing_ms = common_processing_ms + model_filter_ms + wireframe_ms;
      const double active_processing_ms = active_model_filter ? model_processing_ms : legacy_processing_ms;
      const char* status = intrusion ? "OBSERVED_CORE_INTRUSION_CANDIDATE"
                           : raw_core ? "NO_REPORTABLE_INTRUSION_NOISE_IGNORED"
                           : margin ? "OBSERVED_MARGIN_RETURN" : "UNKNOWN";
      const char* reason = intrusion ? "ANY_REPORTABLE_CORE_COMPONENT_IS_INTRUSION_CANDIDATE"
                           : raw_core ? "ONLY_SPARSE_CORE_GROUPS"
                           : margin ? "OBSERVED_RETURN_IN_CLEARANCE_MARGIN"
                                    : "NO_RETURNS_INTERSECT_REFERENCE_NOT_CLEAR";
      std::ostringstream json;
      json << std::fixed << std::setprecision(6)
           << "{\"format\":\"lidar-curve-envelope-v1\",\"status\":\"" << status
           << "\",\"system_status\":\"UNKNOWN\",\"curve_axis_status\":\"CURVE_AXIS_SUPPORTED\","
           << "\"reason\":\"" << reason << "\",\"safety_decision_permitted\":false,"
           << "\"intrusion_candidate_present\":" << (intrusion ? "true" : "false")
           << ",\"reportable_intrusion_candidate_present\":" << (intrusion ? "true" : "false")
           << ",\"raw_core_return_present\":" << (raw_core ? "true" : "false")
           << ",\"all_core_returns_are_intrusion_candidates\":false,\"margin_return_present\":"
           << (margin ? "true" : "false")
           << ",\"compute_backend_requested\":\"direct_cpu_stream\",\"compute_backend_used\":\"cpu\","
           << "\"rail_selection_method\":\"development_candidate\","
           << "\"rail_search_config\":{\"forward_min_m\":" << config.forward_min
           << ",\"forward_max_m\":" << config.forward_max
           << ",\"station_length_m\":" << config.station_length
           << ",\"cell_width_m\":" << config.cell_width << "},"
           << "\"rail_pair_count\":" << active_pairs.size()
           << ",\"observed_rail_pair_count\":" << rails.rail_pairs.size()
           << ",\"forward_extension_method\":\"" << forward_extension_method << "\""
           << ",\"arc_extension_horizon_m\":" << arc_extension_horizon_m
           << ",\"min_arc_radius_m\":" << min_arc_radius_m
           << ",\"max_arc_turn_deg\":" << max_arc_turn_deg
           << ",\"arc_fit_window_pairs\":" << arc_fit_window_pairs
           << ",\"forward_extension_status\":\"" << forward_extension_status << "\""
           << ",\"forward_extension_applied_horizon_m\":" << forward_extension_horizon_m
           << ",\"forward_extension_sample_step_m\":" << forward_extension_sample_step_m
           << ",\"arc_estimated_radius_m\":" << (std::isfinite(arc_estimated_radius_m) ? std::to_string(arc_estimated_radius_m) : "null")
           << ",\"arc_requested_turn_deg\":" << arc_requested_turn_deg
           << ",\"arc_applied_turn_deg\":" << arc_applied_turn_deg
           << ",\"arc_fit_window_pairs_used\":" << arc_fit_window_pairs_used
           << ",\"forward_extrapolated\":" << (active_pairs.size() > rails.rail_pairs.size() ? "true" : "false")
           << ",\"support_start_s_m\":" << active_pairs.front().source_s_m
           << ",\"support_end_s_m\":" << active_pairs.back().source_s_m
           << ",\"observed_support_end_source_s_m\":" << rails.rail_pairs.back().source_s_m
           << ",\"envelope_forward_end_source_s_m\":" << active_pairs.back().source_s_m
           << ",\"core_count\":" << result.core_count
           << ",\"reportable_core_count\":" << result.reportable_core_count
           << ",\"ignored_noise_count\":" << result.ignored_noise_count
           << ",\"margin_count\":" << result.margin_count
           << ",\"outside_reference_count\":" << result.outside_reference_count
           << ",\"unknown_count\":" << result.unknown_count
           << ",\"processing_ms\":" << active_processing_ms
           << ",\"common_processing_ms\":" << common_processing_ms;
      if (legacy_filter_computed) {
        json << ",\"legacy_processing_ms\":" << legacy_processing_ms
             << ",\"legacy_noise_filter_ms\":" << legacy_filter_ms;
      }
      if (model_filter_computed) {
        json << ",\"model_processing_ms\":" << model_processing_ms
             << ",\"model_noise_filter_ms\":" << model_filter_ms;
      }
      json
           << ",\"geometry_basis\":\""
           << (active_pairs.size() <= rails.rail_pairs.size()
               ? "ASSUMED_CURVE_RAIL_AXIS_FROM_SOURCE_XYZ"
               : forward_extension_method == "arc_limited" || forward_extension_method == "arc_clamped"
                   ? "ASSUMED_CURVE_RAIL_AXIS_WITH_LIMITED_FORWARD_ARC_EXTRAPOLATION_SOURCE_XYZ"
                   : "ASSUMED_CURVE_RAIL_AXIS_WITH_FORWARD_TANGENT_EXTRAPOLATION_SOURCE_XYZ")
           << "\","
           << "\"distance_reference\":\"SOURCE_ORIGIN\",\"distance_units\":\"m_ASSUMED\","
           << "\"noise_filter_status\":\"APPLIED\",\"noise_filter_reason\":\""
           << (raw_core && !intrusion ? "ONLY_SPARSE_CORE_GROUPS" : "REPORTABLE_COMPONENT_CHECKED")
           << "\",\"noise_filter_config\":{\"min_reportable_core_points\":"
           << noise_config.min_reportable_core_points
           << ",\"connectivity_radius_m\":" << noise_config.connectivity_radius_m
           << ",\"max_axis_span_m\":" << noise_config.max_axis_span_m
           << ",\"max_average_axis_distance_m\":" << noise_config.max_average_axis_distance_m << "},"
           << "\"noise_filter_mode\":\"" << (active_model_filter ? "candidate_baseline_v2" : "legacy") << "\","
           << "\"model_noise_filter_status\":\""
           << (active_model_filter ? "APPLIED_ACTIVE" : model_filter_computed ? "APPLIED_SHADOW" : "NOT_EVALUATED") << "\","
           << "\"model_noise_filter_name\":\"candidate_baseline_v2\","
           << "\"model_noise_filter_type\":\"forest_lite_mean_tree_probability\"";
      if (model_filter_computed) {
        const bool model_intrusion = model_result.reportable_core_count > 0;
        json << ",\"model_reportable_intrusion_candidate_present\":" << (model_intrusion ? "true" : "false")
             << ",\"model_reportable_core_count\":" << model_result.reportable_core_count
             << ",\"model_ignored_noise_count\":" << model_result.ignored_noise_count;
        if (profile_model_filter) {
          json << ',';
          AppendModelFilterProfileJson(json, model_filter_profile);
        }
      }
      json << ','
           << "\"core_bounds_source_axis\":[" << core.left << ',' << core.right << ',' << core.bottom << ',' << core.top << "],"
           << "\"expanded_bounds_source_axis\":[" << expanded.left << ',' << expanded.right << ','
           << expanded.bottom << ',' << expanded.top << "],\"core_envelope_wireframe_source_xyz\":";
      AppendWireframeJson(json, core_wireframe);
      json << ",\"expanded_envelope_wireframe_source_xyz\":";
      AppendWireframeJson(json, expanded_wireframe);
      json << ",\"curve_axis_polyline_source_xyz\":[";
      for (std::size_t i = 0; i < active_pairs.size(); ++i) {
        const auto& pair = active_pairs[i];
        if (i) json << ',';
        json << '[' << (static_cast<double>(pair.left.x) + pair.right.x) / 2.0 << ','
             << (static_cast<double>(pair.left.y) + pair.right.y) / 2.0 << ','
             << (static_cast<double>(pair.left.z) + pair.right.z) / 2.0 << ']';
      }
      json << "],\"rail_pairs_source_xyz\":[";
      for (std::size_t i = 0; i < active_pairs.size(); ++i) {
        const auto& pair = active_pairs[i];
        if (i) json << ',';
        json << "{\"source_s_m\":" << pair.source_s_m << ",\"left_xyz\":["
             << pair.left.x << ',' << pair.left.y << ',' << pair.left.z
             << "],\"right_xyz\":[" << pair.right.x << ',' << pair.right.y << ','
             << pair.right.z << "],\"observed\":"
             << (i < rails.rail_pairs.size() ? "true" : "false") << "}";
      }
      json << "],\"core_source_indices\":[";
      bool first_core = true;
      for (std::size_t i = 0; i < result.labels.size(); ++i) {
        if (result.labels[i] != lidar_mosmetro3d::Zone::kCore) continue;
        if (!first_core) json << ',';
        json << i;
        first_core = false;
      }
      json << "],\"reportable_core_source_indices\":[";
      bool first_reportable = true;
      for (const auto index : result.reportable_core_source_indices) {
        if (!first_reportable) json << ',';
        json << index;
        first_reportable = false;
      }
      json << "],\"ignored_noise_source_indices\":[";
      bool first_noise = true;
      for (const auto index : result.ignored_noise_source_indices) {
        if (!first_noise) json << ',';
        json << index;
        first_noise = false;
      }
      if (model_filter_computed) {
        json << "],\"model_reportable_core_source_indices\":[";
        bool first_model_reportable = true;
        for (const auto index : model_result.reportable_core_source_indices) {
          if (!first_model_reportable) json << ',';
          json << index;
          first_model_reportable = false;
        }
        json << "],\"model_ignored_noise_source_indices\":[";
        bool first_model_noise = true;
        for (const auto index : model_result.ignored_noise_source_indices) {
          if (!first_model_noise) json << ',';
          json << index;
          first_model_noise = false;
        }
      }
      json << "],\"margin_source_indices\":[";
      bool first_margin = true;
      for (std::size_t i = 0; i < result.labels.size(); ++i) {
        if (result.labels[i] != lidar_mosmetro3d::Zone::kMargin) continue;
        if (!first_margin) json << ',';
        json << i;
        first_margin = false;
      }
      json << ']';
      if (result.nearest_core.source_index != std::numeric_limits<std::size_t>::max()) {
        const auto offset = result.nearest_core.source_index * 3;
        json << ",\"nearest_intrusion_source_index\":" << result.nearest_core.source_index
             << ",\"nearest_intrusion_distance_from_source_origin_m\":"
             << result.nearest_core.distance_from_source_origin_m
             << ",\"nearest_intrusion_xyz\":[" << xyz[offset] << ',' << xyz[offset + 1] << ','
             << xyz[offset + 2] << ']';
      }
      if (result.nearest_reportable_core.source_index != std::numeric_limits<std::size_t>::max()) {
        const auto offset = result.nearest_reportable_core.source_index * 3;
        json << ",\"nearest_reportable_intrusion_source_index\":" << result.nearest_reportable_core.source_index
             << ",\"nearest_reportable_intrusion_distance_from_source_origin_m\":"
             << result.nearest_reportable_core.distance_from_source_origin_m
             << ",\"nearest_reportable_intrusion_xyz\":[" << xyz[offset] << ',' << xyz[offset + 1] << ','
             << xyz[offset + 2] << ']';
      }
      if (result.nearest_margin.source_index != std::numeric_limits<std::size_t>::max()) {
        json << ",\"nearest_margin_source_index\":" << result.nearest_margin.source_index
             << ",\"nearest_margin_distance_from_source_origin_m\":"
             << result.nearest_margin.distance_from_source_origin_m;
      }
      json << '}';
      std::cout << json.str() << "\n" << std::flush;
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "curve_pipeline_stream_cli: " << error.what() << '\n';
    return 1;
  }
}
