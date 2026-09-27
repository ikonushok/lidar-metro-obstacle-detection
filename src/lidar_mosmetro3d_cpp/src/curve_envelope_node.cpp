#include "auto_rails_core.hpp"
#include "cuda_envelope.hpp"
#include "curve_envelope_core.hpp"

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/msg/point_field.hpp>
#include <std_msgs/msg/string.hpp>

#include <cmath>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

class CurveEnvelopeNode final : public rclcpp::Node {
 public:
  CurveEnvelopeNode() : Node("curve_envelope_node") {
    const auto input = declare_parameter<std::string>("input_topic", "/sensing/lidar/hesai128/pointcloud");
    const auto output = declare_parameter<std::string>("output_topic", "/stage_3/curve_envelope_candidate");
    source_frame_ = declare_parameter<std::string>("source_frame", "hesai_lidar");
    compute_backend_ = declare_parameter<std::string>("compute_backend", "cpu");
    noise_filter_mode_ = declare_parameter<std::string>("noise_filter_mode", "baseline_v3");
    temporal_confirmation_enabled_ = declare_parameter<bool>("temporal_confirmation_enabled", true);
    temporal_required_consecutive_frames_ = declare_parameter<int>("temporal_required_consecutive_frames", 2);
    if (temporal_required_consecutive_frames_ <= 0) {
      throw std::invalid_argument("temporal_required_consecutive_frames must be positive");
    }
    rail_selection_method_ = declare_parameter<std::string>("rail_selection_method", "development_candidate");
    forward_extension_method_ = declare_parameter<std::string>("forward_extension_method", "tangent");
    arc_extension_horizon_m_ = declare_parameter<double>("arc_extension_horizon_m", 0.0);
    min_arc_radius_m_ = declare_parameter<double>("min_arc_radius_m", 60.0);
    max_arc_turn_deg_ = declare_parameter<double>("max_arc_turn_deg", 8.0);
    arc_fit_window_pairs_ = declare_parameter<int>("arc_fit_window_pairs", 5);
    rail_config_.forward_min = declare_parameter<double>("rail_forward_min_m", 2.0);
    rail_config_.forward_max = declare_parameter<double>("rail_forward_max_m", 80.0);
    rail_config_.station_length = declare_parameter<double>("rail_station_length_m", 2.0);
    rail_config_.cell_width = declare_parameter<double>("rail_cell_width_m", 0.04);
    const int noise_min_points = declare_parameter<int>("noise_min_reportable_core_points", 22);
    if (noise_min_points <= 0) throw std::invalid_argument("noise_min_reportable_core_points must be positive");
    noise_config_.min_reportable_core_points = static_cast<std::size_t>(noise_min_points);
    noise_config_.connectivity_radius_m = declare_parameter<double>("noise_connectivity_radius_m", 0.25);
    noise_config_.max_axis_span_m = declare_parameter<double>("noise_max_axis_span_m", 1.0);
    noise_config_.max_average_axis_distance_m = declare_parameter<double>("noise_max_average_axis_distance_m", 1.20);
    core_ = {declare_parameter<double>("profile_left_m", -1.4), declare_parameter<double>("profile_right_m", 1.4),
             declare_parameter<double>("profile_bottom_m", 0.0), declare_parameter<double>("profile_top_m", 3.7)};
    expanded_ = {core_.left - declare_parameter<double>("margin_left_m", 0.5),
                 core_.right + declare_parameter<double>("margin_right_m", 0.5),
                 core_.bottom - declare_parameter<double>("margin_bottom_m", 0.5),
                 core_.top + declare_parameter<double>("margin_top_m", 0.5)};
    publisher_ = create_publisher<std_msgs::msg::String>(output, rclcpp::QoS(10));
    subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(input, rclcpp::SensorDataQoS(),
      [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr cloud) { OnCloud(*cloud); });
  }

 private:
  using Field = sensor_msgs::msg::PointField;

  static std::string JsonEscape(const std::string& value) {
    std::ostringstream escaped;
    for (const unsigned char character : value) {
      switch (character) {
        case '"': escaped << "\\\""; break;
        case '\\': escaped << "\\\\"; break;
        case '\b': escaped << "\\b"; break;
        case '\f': escaped << "\\f"; break;
        case '\n': escaped << "\\n"; break;
        case '\r': escaped << "\\r"; break;
        case '\t': escaped << "\\t"; break;
        default:
          if (character < 0x20) {
            escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                    << static_cast<int>(character) << std::dec << std::setfill(' ');
          } else {
            escaped << character;
          }
      }
    }
    return escaped.str();
  }

  static std::string HeaderTimestampNs(const sensor_msgs::msg::PointCloud2& cloud) {
    const auto& stamp = cloud.header.stamp;
    return std::to_string(static_cast<std::int64_t>(stamp.sec) * 1'000'000'000LL +
                          static_cast<std::int64_t>(stamp.nanosec));
  }

  static void AppendWireframeJson(
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

  static void AppendRailPairsJson(
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

  static std::string AutoRailsFailureDiagnosticsJson(
      const lidar_mosmetro3d::AutoRailsResult& rails) {
    std::ostringstream json;
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
    return json.str();
  }

  struct TemporalDecision {
    bool frame_intrusion_candidate_present = false;
    bool confirmed_intrusion_candidate_present = false;
    int consecutive_alarm_frames = 0;
    std::string status = "DISABLED";
  };

  void ResetTemporalState() {
    has_temporal_state_ = false;
    temporal_previous_frame_alarm_ = false;
    temporal_consecutive_alarm_frames_ = 0;
    temporal_last_stamp_ns_.clear();
    temporal_last_confirmed_alarm_ = false;
    temporal_last_status_ = "RESET";
  }

  TemporalDecision ApplyTemporalConfirmation(
      bool frame_intrusion_candidate_present,
      const std::string& header_timestamp_ns) {
    TemporalDecision decision;
    decision.frame_intrusion_candidate_present = frame_intrusion_candidate_present;
    const bool active = (noise_filter_mode_ == "baseline_v3_assist_score" ||
                         noise_filter_mode_ == "baseline_v3") &&
                        temporal_confirmation_enabled_;
    if (!active || temporal_required_consecutive_frames_ <= 1) {
      decision.confirmed_intrusion_candidate_present = frame_intrusion_candidate_present;
      decision.consecutive_alarm_frames = frame_intrusion_candidate_present ? 1 : 0;
      decision.status = (noise_filter_mode_ == "baseline_v3_assist_score" ||
                         noise_filter_mode_ == "baseline_v3")
          ? (temporal_confirmation_enabled_ ? "BYPASS_REQUIRED_FRAMES_1" : "DISABLED")
          : "NOT_APPLIED_LEGACY_MODE";
      return decision;
    }
    if (has_temporal_state_ && header_timestamp_ns == temporal_last_stamp_ns_) {
      decision.confirmed_intrusion_candidate_present = temporal_last_confirmed_alarm_;
      decision.consecutive_alarm_frames = temporal_consecutive_alarm_frames_;
      decision.status = temporal_last_status_;
      return decision;
    }
    if (frame_intrusion_candidate_present) {
      temporal_consecutive_alarm_frames_ = temporal_previous_frame_alarm_
          ? temporal_consecutive_alarm_frames_ + 1
          : 1;
    } else {
      temporal_consecutive_alarm_frames_ = 0;
    }
    const bool confirmed = frame_intrusion_candidate_present &&
        temporal_consecutive_alarm_frames_ >= temporal_required_consecutive_frames_;
    temporal_previous_frame_alarm_ = frame_intrusion_candidate_present;
    has_temporal_state_ = true;
    temporal_last_stamp_ns_ = header_timestamp_ns;
    temporal_last_confirmed_alarm_ = confirmed;
    temporal_last_status_ = confirmed ? "APPLIED_CONFIRMED"
        : frame_intrusion_candidate_present ? "APPLIED_WAITING_FOR_CONSECUTIVE_FRAME"
        : "APPLIED_NO_CURRENT_MODEL_ALARM";
    decision.confirmed_intrusion_candidate_present = confirmed;
    decision.consecutive_alarm_frames = temporal_consecutive_alarm_frames_;
    decision.status = temporal_last_status_;
    return decision;
  }

  void PublishUnknown(const std::string& reason, const sensor_msgs::msg::PointCloud2& cloud,
                      std::size_t points = 0, const std::string& curve_axis_status = "MISSING_CURVE_AXIS",
                      const lidar_mosmetro3d::AutoRailsResult* rails = nullptr) {
    ResetTemporalState();
    std_msgs::msg::String output;
    output.data = "{\"format\":\"lidar-curve-envelope-v1\",\"status\":\"UNKNOWN\",\"system_status\":\"UNKNOWN\","
                  "\"header_timestamp_ns\":\"" + HeaderTimestampNs(cloud) + "\",\"source_frame\":\"" + JsonEscape(cloud.header.frame_id) +
                  "\",\"curve_axis_status\":\"" + curve_axis_status + "\",\"reason\":\"" + reason +
                  "\",\"safety_decision_permitted\":false,\"intrusion_candidate_present\":null,"
                  "\"reportable_intrusion_candidate_present\":null,\"raw_core_return_present\":null,"
                  "\"all_core_returns_are_intrusion_candidates\":false,\"margin_return_present\":null,"
                  "\"compute_backend_requested\":\"" + BackendRequestName() +
                  "\",\"runtime_transport\":\"ros2\",\"noise_filter_mode\":\"" + JsonEscape(noise_filter_mode_) +
                  "\",\"temporal_confirmation_enabled\":" + std::string(temporal_confirmation_enabled_ ? "true" : "false") +
                  ",\"temporal_required_consecutive_frames\":" + std::to_string(temporal_required_consecutive_frames_) +
                  ",\"temporal_confirmation_status\":\"RESET_UNKNOWN\"" +
                  ",\"model_frame_intrusion_candidate_present\":null" +
                  ",\"model_temporal_confirmed_intrusion_candidate_present\":null" +
                  ",\"model_temporal_consecutive_alarm_frames\":0" +
                  ",\"rail_selection_method\":\"" + JsonEscape(rail_selection_method_) +
                  "\",\"forward_extension_method\":\"" + JsonEscape(forward_extension_method_) +
                  "\",\"arc_extension_horizon_m\":" + std::to_string(arc_extension_horizon_m_) +
                  ",\"min_arc_radius_m\":" + std::to_string(min_arc_radius_m_) +
                  ",\"max_arc_turn_deg\":" + std::to_string(max_arc_turn_deg_) +
                  ",\"arc_fit_window_pairs\":" + std::to_string(arc_fit_window_pairs_) +
                  ",\"forward_extension_status\":\"NOT_EVALUATED\""
                  + ",\"rail_search_config\":{\"forward_min_m\":" + std::to_string(rail_config_.forward_min) +
                  ",\"forward_max_m\":" + std::to_string(rail_config_.forward_max) +
                  ",\"station_length_m\":" + std::to_string(rail_config_.station_length) +
                  ",\"cell_width_m\":" + std::to_string(rail_config_.cell_width) + "}" +
                   ",\"point_count\":" + std::to_string(points) +
                  (rails ? "," + AutoRailsFailureDiagnosticsJson(*rails) : "") +
                   ",\"curve_axis_polyline_source_xyz\":[],\"rail_pairs_source_xyz\":[],"
                  "\"core_bounds_source_axis\":null,\"expanded_bounds_source_axis\":null,"
                  "\"core_envelope_wireframe_source_xyz\":[],\"expanded_envelope_wireframe_source_xyz\":[],"
                  "\"core_source_indices\":[],\"reportable_core_source_indices\":[],"
                  "\"ignored_noise_source_indices\":[],\"margin_source_indices\":[]}";
    publisher_->publish(output);
  }

  std::string BackendRequestName() const {
    if (compute_backend_ == "auto" || compute_backend_ == "cpu" || compute_backend_ == "cuda") return compute_backend_;
    return "INVALID";
  }

  void OnCloud(const sensor_msgs::msg::PointCloud2& cloud) {
    const auto started = std::chrono::steady_clock::now();
    if (cloud.header.frame_id != source_frame_) return PublishUnknown("UNSUPPORTED_SOURCE_FRAME", cloud);
    if (cloud.is_bigendian != IsHostBigEndian()) return PublishUnknown("UNSUPPORTED_POINTCLOUD_ENDIANNESS", cloud);
    std::unordered_map<std::string, Field> fields;
    for (const auto& field : cloud.fields) fields[field.name] = field;
    if (!fields.count("x") || !fields.count("y") || !fields.count("z") ||
        fields["x"].datatype != Field::FLOAT32 || fields["y"].datatype != Field::FLOAT32 || fields["z"].datatype != Field::FLOAT32 ||
        fields["x"].count != 1 || fields["y"].count != 1 || fields["z"].count != 1 ||
        cloud.point_step == 0 || fields["x"].offset + 4 > cloud.point_step || fields["y"].offset + 4 > cloud.point_step || fields["z"].offset + 4 > cloud.point_step ||
        cloud.row_step < cloud.width * cloud.point_step || cloud.data.size() < static_cast<std::size_t>(cloud.row_step) * cloud.height)
      return PublishUnknown("UNSUPPORTED_POINTCLOUD_XYZ_SCHEMA", cloud);
    std::vector<float> xyz; xyz.reserve(static_cast<std::size_t>(cloud.width) * cloud.height * 3);
    for (std::uint32_t row = 0; row < cloud.height; ++row) for (std::uint32_t column = 0; column < cloud.width; ++column) {
      const auto* point = cloud.data.data() + static_cast<std::size_t>(row) * cloud.row_step + static_cast<std::size_t>(column) * cloud.point_step;
      float x, y, z;
      std::memcpy(&x, point + fields["x"].offset, sizeof(float));
      std::memcpy(&y, point + fields["y"].offset, sizeof(float));
      std::memcpy(&z, point + fields["z"].offset, sizeof(float));
      if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) return PublishUnknown("NONFINITE_XYZ", cloud);
      xyz.insert(xyz.end(), {x, y, z});
    }
    if (!(core_.left < core_.right && core_.bottom < core_.top && expanded_.left <= core_.left && expanded_.right >= core_.right &&
           expanded_.bottom <= core_.bottom && expanded_.top >= core_.top)) return PublishUnknown("INVALID_ENVELOPE", cloud, xyz.size() / 3);
    if (compute_backend_ != "auto" && compute_backend_ != "cpu" && compute_backend_ != "cuda")
      return PublishUnknown("INVALID_COMPUTE_BACKEND", cloud, xyz.size() / 3);
    if (noise_filter_mode_ != "legacy" && noise_filter_mode_ != "baseline_v3_assist_score" &&
        noise_filter_mode_ != "baseline_v3")
      return PublishUnknown("INVALID_NOISE_FILTER_MODE", cloud, xyz.size() / 3);
    lidar_mosmetro3d::RailSelectionMethod selection;
    if (rail_selection_method_ == "baseline") selection = lidar_mosmetro3d::RailSelectionMethod::kBaseline;
    else if (rail_selection_method_ == "development_candidate") selection = lidar_mosmetro3d::RailSelectionMethod::kDevelopmentCandidate;
    else return PublishUnknown("INVALID_RAIL_SELECTION_METHOD", cloud, xyz.size() / 3);
    if (forward_extension_method_ != "tangent" && forward_extension_method_ != "arc_limited" &&
        forward_extension_method_ != "arc_clamped")
      return PublishUnknown("INVALID_FORWARD_EXTENSION_METHOD", cloud, xyz.size() / 3);
    if (!std::isfinite(arc_extension_horizon_m_) || arc_extension_horizon_m_ < 0.0)
      return PublishUnknown("INVALID_ARC_EXTENSION_HORIZON", cloud, xyz.size() / 3);
    if (!std::isfinite(min_arc_radius_m_) || min_arc_radius_m_ <= 0.0 ||
        !std::isfinite(max_arc_turn_deg_) || max_arc_turn_deg_ <= 0.0)
      return PublishUnknown("INVALID_ARC_CLAMP_PARAMETERS", cloud, xyz.size() / 3);
    if (arc_fit_window_pairs_ < 3)
      return PublishUnknown("INVALID_ARC_FIT_WINDOW", cloud, xyz.size() / 3);
    const auto rails = lidar_mosmetro3d::DetectAutoRails(xyz.data(), xyz.size() / 3, rail_config_, selection);
    if (rails.rail_pairs.size() < 2) return PublishUnknown(rails.reason, cloud, xyz.size() / 3,
                                                           "MISSING_CURVE_AXIS", &rails);
    const std::size_t observed_rail_pair_count = rails.rail_pairs.size();
    std::vector<lidar_mosmetro3d::RailPair> envelope_pairs;
    std::string forward_extension_status;
    double forward_extension_horizon_m = 0.0;
    double forward_extension_sample_step_m = 0.0;
    double arc_estimated_radius_m = std::numeric_limits<double>::quiet_NaN();
    double arc_requested_turn_deg = 0.0;
    double arc_applied_turn_deg = 0.0;
    std::size_t arc_fit_window_pairs_used = 0;
    if (forward_extension_method_ == "tangent") {
      envelope_pairs = lidar_mosmetro3d::ExtendRailPairsForward(
          rails.rail_pairs, rail_config_.forward_max);
      forward_extension_status = envelope_pairs.size() > observed_rail_pair_count
          ? "TANGENT_APPLIED" : "AT_FORWARD_LIMIT";
      forward_extension_horizon_m = envelope_pairs.back().source_s_m - rails.rail_pairs.back().source_s_m;
    } else if (forward_extension_method_ == "arc_limited") {
      const auto arc_extension = lidar_mosmetro3d::ExtendRailPairsForwardArcLimited(
          rails.rail_pairs, arc_extension_horizon_m_, rail_config_.forward_max);
      envelope_pairs = arc_extension.rail_pairs;
      forward_extension_status = lidar_mosmetro3d::ArcLimitedExtensionStatusName(arc_extension.status);
      forward_extension_horizon_m = arc_extension.applied_horizon_m;
      forward_extension_sample_step_m = arc_extension.sample_step_m;
      arc_estimated_radius_m = arc_extension.estimated_radius_m;
      arc_requested_turn_deg = arc_extension.requested_turn_deg;
      arc_applied_turn_deg = arc_extension.applied_turn_deg;
      arc_fit_window_pairs_used = arc_extension.fit_window_pairs;
    } else if (forward_extension_method_ == "arc_clamped") {
      const auto arc_extension = lidar_mosmetro3d::ExtendRailPairsForwardArcClamped(
          rails.rail_pairs, arc_extension_horizon_m_, rail_config_.forward_max,
          min_arc_radius_m_, max_arc_turn_deg_, static_cast<std::size_t>(arc_fit_window_pairs_));
      envelope_pairs = arc_extension.rail_pairs;
      forward_extension_status = lidar_mosmetro3d::ArcLimitedExtensionStatusName(arc_extension.status);
      forward_extension_horizon_m = arc_extension.applied_horizon_m;
      forward_extension_sample_step_m = arc_extension.sample_step_m;
      arc_estimated_radius_m = arc_extension.estimated_radius_m;
      arc_requested_turn_deg = arc_extension.requested_turn_deg;
      arc_applied_turn_deg = arc_extension.applied_turn_deg;
      arc_fit_window_pairs_used = arc_extension.fit_window_pairs;
    }
    const bool forward_extrapolated = envelope_pairs.size() > observed_rail_pair_count;
    // Model mode classifies raw CORE directly, without legacy suppression first.
    auto envelope_noise_config = noise_config_;
    envelope_noise_config.enabled = noise_filter_mode_ == "legacy";
    lidar_mosmetro3d::AnalysisResult result;
    std::string backend_used = "cpu";
    std::string backend_fallback_reason;
    if (compute_backend_ == "auto" || compute_backend_ == "cuda") {
      std::string cuda_reason;
      if (lidar_mosmetro3d::CudaEnvelopeAvailable(&cuda_reason)) {
        try {
          result = lidar_mosmetro3d::AnalyzeCurveEnvelopeCuda(
              xyz.data(), xyz.size() / 3, envelope_pairs, core_, expanded_, envelope_noise_config);
          backend_used = "cuda";
        } catch (const std::exception&) {}
      }
      if (backend_used != "cuda") {
        if (compute_backend_ == "cuda") return PublishUnknown("CUDA_UNAVAILABLE", cloud, xyz.size() / 3, "CURVE_AXIS_SUPPORTED");
        result = lidar_mosmetro3d::AnalyzeCurveEnvelope(
            xyz.data(), xyz.size() / 3, envelope_pairs, core_, expanded_, envelope_noise_config);
        backend_fallback_reason = "CUDA_UNAVAILABLE";
      }
    } else {
      result = lidar_mosmetro3d::AnalyzeCurveEnvelope(
          xyz.data(), xyz.size() / 3, envelope_pairs, core_, expanded_, envelope_noise_config);
    }
    if (noise_filter_mode_ == "baseline_v3_assist_score") {
      lidar_mosmetro3d::ApplyBaselineV3AssistScore(
          xyz.data(), xyz.size() / 3, result, noise_config_.connectivity_radius_m);
    } else if (noise_filter_mode_ == "baseline_v3") {
      lidar_mosmetro3d::ApplyBaselineV3(
          xyz.data(), xyz.size() / 3, result, noise_config_.connectivity_radius_m);
    }
    const auto core_wireframe = lidar_mosmetro3d::BuildCurveEnvelopeWireframe(envelope_pairs, core_);
    const auto expanded_wireframe = lidar_mosmetro3d::BuildCurveEnvelopeWireframe(envelope_pairs, expanded_);
    const auto elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    const bool raw_core_return_present = result.core_count > 0;
    const bool baseline_v3_mode = noise_filter_mode_ == "baseline_v3";
    const bool baseline_v3_geometry_intrusion =
        baseline_v3_mode && result.baseline_v3_geometry_obstacle_count > 0;
    const bool baseline_v3_model_frame_intrusion =
        baseline_v3_mode && result.baseline_v3_model_assist_count > 0;
    const bool baseline_v3_boundary_warning =
        baseline_v3_mode && result.baseline_v3_boundary_warning_count > 0;
    const bool frame_intrusion_candidate_present = baseline_v3_mode
        ? baseline_v3_model_frame_intrusion
        : result.reportable_core_count > 0;
    const auto header_timestamp_ns = HeaderTimestampNs(cloud);
    const auto temporal_decision = ApplyTemporalConfirmation(
        frame_intrusion_candidate_present, header_timestamp_ns);
    const bool intrusion_candidate_present = baseline_v3_mode
        ? (baseline_v3_geometry_intrusion ||
           temporal_decision.confirmed_intrusion_candidate_present)
        : temporal_decision.confirmed_intrusion_candidate_present;
    const bool model_temporal_confirmed_intrusion_candidate_present =
        temporal_decision.confirmed_intrusion_candidate_present;
    const bool margin_return_present = result.margin_count > 0;
    const char* status = intrusion_candidate_present ? "OBSERVED_CORE_INTRUSION_CANDIDATE"
                         : baseline_v3_boundary_warning ? "OBSERVED_BOUNDARY_WARNING"
                         : baseline_v3_mode && raw_core_return_present ? "UNKNOWN"
                         : frame_intrusion_candidate_present ? "UNCONFIRMED_CORE_INTRUSION_CANDIDATE"
                         : raw_core_return_present ? "NO_REPORTABLE_INTRUSION_NOISE_IGNORED"
                         : margin_return_present ? "OBSERVED_MARGIN_RETURN" : "UNKNOWN";
    const char* reason = intrusion_candidate_present && baseline_v3_mode ? "BASELINE_V3_CONFIRMED_INTRUSION_CANDIDATE"
                         : intrusion_candidate_present ? "ANY_REPORTABLE_CORE_COMPONENT_IS_INTRUSION_CANDIDATE"
                         : baseline_v3_boundary_warning ? "BASELINE_V3_BOUNDARY_WARNING_NOT_OBSTACLE"
                         : baseline_v3_mode && frame_intrusion_candidate_present ? "BASELINE_V3_MODEL_ASSIST_WAITING_FOR_TEMPORAL_CONFIRMATION"
                         : baseline_v3_mode && raw_core_return_present ? "BASELINE_V3_WEAK_OR_UNCONFIRMED_CORE_UNKNOWN_NOT_CLEAR"
                         : frame_intrusion_candidate_present ? "MODEL_CANDIDATE_WAITING_FOR_TEMPORAL_CONFIRMATION"
                         : raw_core_return_present ? "ONLY_SPARSE_CORE_GROUPS"
                         : margin_return_present ? "OBSERVED_RETURN_IN_CLEARANCE_MARGIN"
                         : "NO_RETURNS_INTERSECT_REFERENCE_NOT_CLEAR";
    std_msgs::msg::String output;
    std::ostringstream json;
    json << std::fixed << std::setprecision(6)
         << "{\"format\":\"lidar-curve-envelope-v1\",\"status\":\"" << status
         << "\",\"system_status\":\"UNKNOWN\",\"header_timestamp_ns\":\"" << header_timestamp_ns
         << "\",\"source_frame\":\"" << JsonEscape(cloud.header.frame_id)
         << "\",\"curve_axis_status\":\"CURVE_AXIS_SUPPORTED\","
        << "\"reason\":\"" << reason << "\",\"safety_decision_permitted\":false,"
        << "\"intrusion_candidate_present\":" << (intrusion_candidate_present ? "true" : "false")
        << ",\"reportable_intrusion_candidate_present\":" << (intrusion_candidate_present ? "true" : "false")
        << ",\"model_frame_intrusion_candidate_present\":"
        << (frame_intrusion_candidate_present ? "true" : "false")
        << ",\"model_temporal_confirmed_intrusion_candidate_present\":"
        << (model_temporal_confirmed_intrusion_candidate_present ? "true" : "false")
        << ",\"model_temporal_consecutive_alarm_frames\":"
        << temporal_decision.consecutive_alarm_frames
        << ",\"raw_core_return_present\":" << (raw_core_return_present ? "true" : "false")
        << ",\"all_core_returns_are_intrusion_candidates\":false,\"margin_return_present\":" << (margin_return_present ? "true" : "false")
         << ",\"compute_backend_requested\":\"" << BackendRequestName() << "\",\"compute_backend_used\":\"" << backend_used << "\","
         << "\"runtime_transport\":\"ros2\",\"noise_filter_mode\":\"" << noise_filter_mode_ << "\","
         << "\"noise_filter_name\":\"" << (noise_filter_mode_ == "baseline_v3_assist_score" ? "baseline_v3_assist_score" :
                                           noise_filter_mode_ == "baseline_v3" ? "baseline_v3" : "legacy_geometry") << "\","
         << "\"rail_selection_method\":\"" << lidar_mosmetro3d::RailSelectionMethodName(selection) << "\","
         << "\"rail_search_config\":{\"forward_min_m\":" << rail_config_.forward_min
         << ",\"forward_max_m\":" << rail_config_.forward_max
         << ",\"station_length_m\":" << rail_config_.station_length
         << ",\"cell_width_m\":" << rail_config_.cell_width << "},"
        << "\"rail_pair_count\":" << envelope_pairs.size() << ",\"core_count\":" << result.core_count
        << ",\"reportable_core_count\":" << result.reportable_core_count
        << ",\"ignored_noise_count\":" << result.ignored_noise_count
        << ",\"baseline_v3_geometry_obstacle_count\":" << result.baseline_v3_geometry_obstacle_count
        << ",\"baseline_v3_boundary_warning_count\":" << result.baseline_v3_boundary_warning_count
        << ",\"baseline_v3_model_assist_count\":" << result.baseline_v3_model_assist_count
        << ",\"baseline_v3_geometry_intrusion_candidate_present\":"
        << (baseline_v3_geometry_intrusion ? "true" : "false")
        << ",\"baseline_v3_boundary_warning_present\":"
        << (baseline_v3_boundary_warning ? "true" : "false")
        << ",\"baseline_v3_model_assist_frame_candidate_present\":"
        << (baseline_v3_model_frame_intrusion ? "true" : "false")
        << ",\"margin_count\":" << result.margin_count << ",\"outside_reference_count\":" << result.outside_reference_count
        << ",\"unknown_count\":" << result.unknown_count << ",\"processing_ms\":" << elapsed;
    const char* geometry_basis = !forward_extrapolated ? "ASSUMED_CURVE_RAIL_AXIS_FROM_SOURCE_XYZ"
        : forward_extension_method_ == "arc_limited" || forward_extension_method_ == "arc_clamped"
            ? "ASSUMED_CURVE_RAIL_AXIS_WITH_LIMITED_FORWARD_ARC_EXTRAPOLATION_SOURCE_XYZ"
            : "ASSUMED_CURVE_RAIL_AXIS_WITH_FORWARD_TANGENT_EXTRAPOLATION_SOURCE_XYZ";
    json << ",\"geometry_basis\":\"" << geometry_basis << "\",\"distance_reference\":\"SOURCE_ORIGIN\",\"distance_units\":\"m_ASSUMED\""
         << ",\"noise_filter_status\":\"APPLIED\",\"noise_filter_reason\":\""
         << (raw_core_return_present && !frame_intrusion_candidate_present ? "ONLY_SPARSE_CORE_GROUPS" : "REPORTABLE_COMPONENT_CHECKED")
         << "\",\"noise_filter_config\":{\"connectivity_radius_m\":" << noise_config_.connectivity_radius_m;
    if (noise_filter_mode_ == "legacy") {
      json << ",\"min_reportable_core_points\":" << noise_config_.min_reportable_core_points
           << ",\"max_axis_span_m\":" << noise_config_.max_axis_span_m
           << ",\"max_average_axis_distance_m\":" << noise_config_.max_average_axis_distance_m;
    }
    json << "}"
         << ",\"temporal_confirmation_enabled\":" << (temporal_confirmation_enabled_ ? "true" : "false")
         << ",\"temporal_required_consecutive_frames\":" << temporal_required_consecutive_frames_
         << ",\"temporal_confirmation_status\":\"" << temporal_decision.status << "\""
         << ",\"observed_rail_pair_count\":" << observed_rail_pair_count
         << ",\"forward_extension_method\":\"" << forward_extension_method_ << "\""
         << ",\"arc_extension_horizon_m\":" << arc_extension_horizon_m_
         << ",\"min_arc_radius_m\":" << min_arc_radius_m_
         << ",\"max_arc_turn_deg\":" << max_arc_turn_deg_
         << ",\"arc_fit_window_pairs\":" << arc_fit_window_pairs_
         << ",\"forward_extension_status\":\"" << forward_extension_status << "\""
         << ",\"forward_extension_applied_horizon_m\":" << forward_extension_horizon_m
         << ",\"forward_extension_sample_step_m\":" << forward_extension_sample_step_m
         << ",\"arc_estimated_radius_m\":" << (std::isfinite(arc_estimated_radius_m) ? std::to_string(arc_estimated_radius_m) : "null")
         << ",\"arc_requested_turn_deg\":" << arc_requested_turn_deg
         << ",\"arc_applied_turn_deg\":" << arc_applied_turn_deg
         << ",\"arc_fit_window_pairs_used\":" << arc_fit_window_pairs_used
         << ",\"forward_extrapolated\":" << (forward_extrapolated ? "true" : "false")
         << ",\"observed_support_end_source_s_m\":" << rails.rail_pairs.back().source_s_m
         << ",\"envelope_forward_end_source_s_m\":" << envelope_pairs.back().source_s_m
         << ",\"core_bounds_source_axis\":[" << core_.left << ',' << core_.right << ',' << core_.bottom << ',' << core_.top << ']'
         << ",\"expanded_bounds_source_axis\":[" << expanded_.left << ',' << expanded_.right << ',' << expanded_.bottom << ',' << expanded_.top << ']'
         << ",\"core_envelope_wireframe_source_xyz\":";
    AppendWireframeJson(json, core_wireframe);
    json << ",\"expanded_envelope_wireframe_source_xyz\":";
    AppendWireframeJson(json, expanded_wireframe);
    json << ",\"curve_axis_polyline_source_xyz\":[";
    for (std::size_t i = 0; i < envelope_pairs.size(); ++i) {
      const auto& pair = envelope_pairs[i];
      if (i) json << ',';
      json << '[' << (static_cast<double>(pair.left.x) + pair.right.x) / 2.0 << ','
           << (static_cast<double>(pair.left.y) + pair.right.y) / 2.0 << ','
           << (static_cast<double>(pair.left.z) + pair.right.z) / 2.0 << ']';
    }
    json << "],\"rail_pairs_source_xyz\":[";
    for (std::size_t i = 0; i < envelope_pairs.size(); ++i) {
      const auto& pair = envelope_pairs[i];
      if (i) json << ',';
      json << "{\"source_s_m\":" << pair.source_s_m << ",\"left_xyz\":[" << pair.left.x << ',' << pair.left.y << ',' << pair.left.z
           << "],\"right_xyz\":[" << pair.right.x << ',' << pair.right.y << ',' << pair.right.z
           << "],\"observed\":" << (i < observed_rail_pair_count ? "true" : "false") << "}";
    }
    json << "],\"core_source_indices\":[";
    bool first_core_index = true;
    for (std::size_t i = 0; i < result.labels.size(); ++i) if (result.labels[i] == lidar_mosmetro3d::Zone::kCore) {
      if (!first_core_index) json << ',';
      json << i;
      first_core_index = false;
    }
    json << "],\"reportable_core_source_indices\":[";
    bool first_reportable_index = true;
    for (const auto index : result.reportable_core_source_indices) {
      if (!first_reportable_index) json << ',';
      json << index;
      first_reportable_index = false;
    }
    json << "],\"ignored_noise_source_indices\":[";
    bool first_noise_index = true;
    for (const auto index : result.ignored_noise_source_indices) {
      if (!first_noise_index) json << ',';
      json << index;
      first_noise_index = false;
    }
    json << "],\"margin_source_indices\":[";
    bool first_margin_index = true;
    for (std::size_t i = 0; i < result.labels.size(); ++i) if (result.labels[i] == lidar_mosmetro3d::Zone::kMargin) {
      if (!first_margin_index) json << ',';
      json << i;
      first_margin_index = false;
    }
    json << ']';
    if (!backend_fallback_reason.empty()) json << ",\"compute_backend_fallback\":\"" << backend_fallback_reason << "\"";
    if (result.nearest_core.source_index != std::numeric_limits<std::size_t>::max())
      json << ",\"nearest_intrusion_source_index\":" << result.nearest_core.source_index
           << ",\"nearest_intrusion_distance_from_source_origin_m\":" << result.nearest_core.distance_from_source_origin_m;
    if (result.nearest_core.source_index < xyz.size() / 3) {
      const auto offset = result.nearest_core.source_index * 3;
      json << ",\"nearest_intrusion_xyz\":[" << xyz[offset] << ',' << xyz[offset + 1] << ',' << xyz[offset + 2] << ']';
    }
    if (result.nearest_reportable_core.source_index != std::numeric_limits<std::size_t>::max())
      json << ",\"nearest_reportable_intrusion_source_index\":" << result.nearest_reportable_core.source_index
           << ",\"nearest_reportable_intrusion_distance_from_source_origin_m\":"
           << result.nearest_reportable_core.distance_from_source_origin_m;
    if (result.nearest_reportable_core.source_index < xyz.size() / 3) {
      const auto offset = result.nearest_reportable_core.source_index * 3;
      json << ",\"nearest_reportable_intrusion_xyz\":[" << xyz[offset] << ',' << xyz[offset + 1] << ',' << xyz[offset + 2] << ']';
    }
    if (result.nearest_margin.source_index != std::numeric_limits<std::size_t>::max())
      json << ",\"nearest_margin_source_index\":" << result.nearest_margin.source_index
           << ",\"nearest_margin_distance_from_source_origin_m\":" << result.nearest_margin.distance_from_source_origin_m;
    json << "}";
    output.data = json.str(); publisher_->publish(output);
  }

  static bool IsHostBigEndian() { const std::uint16_t value = 1; return *reinterpret_cast<const std::uint8_t*>(&value) == 0; }

  lidar_mosmetro3d::Bounds core_{};
  lidar_mosmetro3d::Bounds expanded_{};
  std::string source_frame_;
  std::string compute_backend_;
  std::string noise_filter_mode_;
  bool temporal_confirmation_enabled_ = true;
  int temporal_required_consecutive_frames_ = 2;
  bool has_temporal_state_ = false;
  bool temporal_previous_frame_alarm_ = false;
  int temporal_consecutive_alarm_frames_ = 0;
  std::string temporal_last_stamp_ns_;
  bool temporal_last_confirmed_alarm_ = false;
  std::string temporal_last_status_ = "RESET";
  std::string rail_selection_method_;
  std::string forward_extension_method_;
  double arc_extension_horizon_m_ = 0.0;
  double min_arc_radius_m_ = 60.0;
  double max_arc_turn_deg_ = 8.0;
  int arc_fit_window_pairs_ = 5;
  lidar_mosmetro3d::AutoRailsConfig rail_config_{};
  lidar_mosmetro3d::CoreNoiseFilterConfig noise_config_{};
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
};

}  // namespace

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CurveEnvelopeNode>());
  rclcpp::shutdown();
}
