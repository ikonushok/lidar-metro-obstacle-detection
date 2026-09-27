#include "curve_envelope_core.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace lidar_mosmetro3d {
namespace {

constexpr double kTolerance = 1e-6;
constexpr double kPi = 3.14159265358979323846;

struct Segment {
  Point3f a;
  double tx;
  double ty;
  double nx;
  double ny;
  double dz;
  double length;
  double source_s_start;
  double source_s_end;
};

struct AxisProjection {
  double source_s_m = std::numeric_limits<double>::quiet_NaN();
  double distance_m = std::numeric_limits<double>::infinity();
};

struct ComponentAxisStats {
  bool valid = false;
  double span_m = 0.0;
  double average_distance_m = 0.0;
};

struct ComponentShapeStats {
  std::size_t point_count = 0;
  double min_x = std::numeric_limits<double>::infinity();
  double min_y = std::numeric_limits<double>::infinity();
  double min_z = std::numeric_limits<double>::infinity();
  double max_x = -std::numeric_limits<double>::infinity();
  double max_y = -std::numeric_limits<double>::infinity();
  double max_z = -std::numeric_limits<double>::infinity();
  double centroid_x = 0.0;
  double centroid_y = 0.0;
  double centroid_z = 0.0;
  double nearest_distance_m = std::numeric_limits<double>::infinity();
};

struct ArcGeometry {
  bool valid = false;
  double centre_x = 0.0;
  double centre_y = 0.0;
  double radius_m = std::numeric_limits<double>::quiet_NaN();
  double direction = 1.0;
  double station_step_m = 0.0;
};

struct SpatialCell {
  std::int64_t x;
  std::int64_t y;
  std::int64_t z;

  bool operator==(const SpatialCell& other) const {
    return x == other.x && y == other.y && z == other.z;
  }
};

struct SpatialCellHash {
  std::size_t operator()(const SpatialCell& cell) const {
    const auto mix = [](std::uint64_t value) {
      value ^= value >> 30;
      value *= 0xbf58476d1ce4e5b9ULL;
      value ^= value >> 27;
      value *= 0x94d049bb133111ebULL;
      value ^= value >> 31;
      return value;
    };
    const std::uint64_t x = mix(static_cast<std::uint64_t>(cell.x));
    const std::uint64_t y = mix(static_cast<std::uint64_t>(cell.y) + 0x9e3779b97f4a7c15ULL);
    const std::uint64_t z = mix(static_cast<std::uint64_t>(cell.z) + 0x243f6a8885a308d3ULL);
    return static_cast<std::size_t>(x ^ (y << 1) ^ (z << 2));
  }
};

using SpatialIndex = std::unordered_map<SpatialCell, std::vector<std::size_t>, SpatialCellHash>;

bool IsFinite(const Point3f& point) {
  return std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z);
}

SpatialCell PointCell(const Point3f& point, double cell_size_m) {
  return {
      static_cast<std::int64_t>(std::floor(static_cast<double>(point.x) / cell_size_m)),
      static_cast<std::int64_t>(std::floor(static_cast<double>(point.y) / cell_size_m)),
      static_cast<std::int64_t>(std::floor(static_cast<double>(point.z) / cell_size_m)),
  };
}

SpatialIndex BuildSpatialIndex(const float* xyz, const std::vector<std::size_t>& source_indices,
                               double cell_size_m) {
  SpatialIndex index;
  index.reserve(source_indices.size());
  for (std::size_t local = 0; local < source_indices.size(); ++local) {
    const std::size_t source_index = source_indices[local];
    const Point3f point{xyz[source_index * 3], xyz[source_index * 3 + 1], xyz[source_index * 3 + 2]};
    if (!IsFinite(point)) throw std::invalid_argument("xyz must be finite");
    index[PointCell(point, cell_size_m)].push_back(local);
  }
  return index;
}

bool InBounds(const Bounds& bounds, double lateral, double height) {
  return lateral >= bounds.left - kTolerance && lateral <= bounds.right + kTolerance &&
         height >= bounds.bottom - kTolerance && height <= bounds.top + kTolerance;
}

bool ValidBounds(const Bounds& bounds) {
  return bounds.left < bounds.right && bounds.bottom < bounds.top;
}

std::vector<Segment> BuildSegments(const std::vector<RailPair>& pairs) {
  std::vector<Segment> segments;
  if (pairs.size() < 2) return segments;
  segments.reserve(pairs.size() - 1);
  for (std::size_t index = 0; index + 1 < pairs.size(); ++index) {
    const Point3f a{static_cast<float>((pairs[index].left.x + pairs[index].right.x) * 0.5),
                    static_cast<float>((pairs[index].left.y + pairs[index].right.y) * 0.5),
                    static_cast<float>((pairs[index].left.z + pairs[index].right.z) * 0.5)};
    const Point3f b{static_cast<float>((pairs[index + 1].left.x + pairs[index + 1].right.x) * 0.5),
                    static_cast<float>((pairs[index + 1].left.y + pairs[index + 1].right.y) * 0.5),
                    static_cast<float>((pairs[index + 1].left.z + pairs[index + 1].right.z) * 0.5)};
    const double dx = static_cast<double>(b.x) - a.x;
    const double dy = static_cast<double>(b.y) - a.y;
    const double length = std::hypot(dx, dy);
    if (length < kTolerance) throw std::invalid_argument("adjacent curve sections must differ");
    double nx = dy / length;
    double ny = -dx / length;
    const double side_x = static_cast<double>(pairs[index].left.x) - pairs[index].right.x;
    const double side_y = static_cast<double>(pairs[index].left.y) - pairs[index].right.y;
    if (nx * side_x + ny * side_y < 0.0) {
      nx = -nx;
      ny = -ny;
    }
    segments.push_back({a, dx / length, dy / length, nx, ny,
                        static_cast<double>(b.z) - a.z, length,
                        pairs[index].source_s_m, pairs[index + 1].source_s_m});
  }
  return segments;
}

Point3f SegmentPoint(const Segment& segment, double station,
                     double lateral, double height) {
  return {
      static_cast<float>(segment.a.x + segment.tx * station + segment.nx * lateral),
      static_cast<float>(segment.a.y + segment.ty * station + segment.ny * lateral),
      static_cast<float>(segment.a.z + segment.dz * station / segment.length + height),
  };
}

AxisProjection ProjectToAxis(const Point3f& point, const std::vector<Segment>& segments) {
  AxisProjection best;
  for (const auto& segment : segments) {
    const double dx = static_cast<double>(point.x) - segment.a.x;
    const double dy = static_cast<double>(point.y) - segment.a.y;
    const double station = std::clamp(dx * segment.tx + dy * segment.ty, 0.0, segment.length);
    const double t = station / segment.length;
    const Point3f nearest{
        static_cast<float>(segment.a.x + segment.tx * station),
        static_cast<float>(segment.a.y + segment.ty * station),
        static_cast<float>(segment.a.z + segment.dz * t),
    };
    const double px = static_cast<double>(point.x) - nearest.x;
    const double py = static_cast<double>(point.y) - nearest.y;
    const double pz = static_cast<double>(point.z) - nearest.z;
    const double distance = std::hypot(std::hypot(px, py), pz);
    if (distance >= best.distance_m) continue;
    best.distance_m = distance;
    best.source_s_m = segment.source_s_start + t * (segment.source_s_end - segment.source_s_start);
  }
  return best;
}

ComponentAxisStats ComputeComponentAxisStats(const float* xyz,
                                             const std::vector<std::size_t>& component,
                                             const std::vector<Segment>& segments) {
  if (segments.empty()) return {};
  double min_s = std::numeric_limits<double>::infinity();
  double max_s = -std::numeric_limits<double>::infinity();
  double distance_sum = 0.0;
  std::size_t valid = 0;
  for (const std::size_t source_index : component) {
    const Point3f point{xyz[source_index * 3], xyz[source_index * 3 + 1], xyz[source_index * 3 + 2]};
    const auto projection = ProjectToAxis(point, segments);
    if (!std::isfinite(projection.source_s_m) || !std::isfinite(projection.distance_m)) continue;
    min_s = std::min(min_s, projection.source_s_m);
    max_s = std::max(max_s, projection.source_s_m);
    distance_sum += projection.distance_m;
    ++valid;
  }
  if (!valid) return {};
  return {true, max_s - min_s, distance_sum / static_cast<double>(valid)};
}

ComponentShapeStats ComputeComponentShapeStats(
    const float* xyz, const std::vector<std::size_t>& component) {
  if (component.empty()) throw std::invalid_argument("component must not be empty");
  ComponentShapeStats stats;
  stats.point_count = component.size();
  double sum_x = 0.0;
  double sum_y = 0.0;
  double sum_z = 0.0;
  for (const std::size_t source_index : component) {
    const Point3f point{xyz[source_index * 3], xyz[source_index * 3 + 1], xyz[source_index * 3 + 2]};
    if (!IsFinite(point)) throw std::invalid_argument("xyz must be finite");
    stats.min_x = std::min(stats.min_x, static_cast<double>(point.x));
    stats.min_y = std::min(stats.min_y, static_cast<double>(point.y));
    stats.min_z = std::min(stats.min_z, static_cast<double>(point.z));
    stats.max_x = std::max(stats.max_x, static_cast<double>(point.x));
    stats.max_y = std::max(stats.max_y, static_cast<double>(point.y));
    stats.max_z = std::max(stats.max_z, static_cast<double>(point.z));
    sum_x += point.x;
    sum_y += point.y;
    sum_z += point.z;
    stats.nearest_distance_m = std::min(stats.nearest_distance_m, std::hypot(
        static_cast<double>(point.x), point.y, point.z));
  }
  const double count = static_cast<double>(component.size());
  stats.centroid_x = sum_x / count;
  stats.centroid_y = sum_y / count;
  stats.centroid_z = sum_z / count;
  return stats;
}

bool BaselineV3BoundaryWarning(const ComponentShapeStats& stats) {
  const double extent_x = stats.max_x - stats.min_x;
  const double extent_y = stats.max_y - stats.min_y;
  const double extent_z = stats.max_z - stats.min_z;
  return (stats.centroid_x < -1.30 && extent_x < 0.25 && extent_z > 1.50) ||
         (stats.centroid_z > 1.00 && extent_x > 1.00 && extent_y > 1.00 && extent_z > 0.30);
}

void ResetReportableOutputs(AnalysisResult& result) {
  result.reportable_core_count = 0;
  result.ignored_noise_count = 0;
  result.baseline_v3_geometry_obstacle_count = 0;
  result.baseline_v3_boundary_warning_count = 0;
  result.baseline_v3_model_assist_count = 0;
  result.reportable_core_source_indices.clear();
  result.ignored_noise_source_indices.clear();
  result.baseline_v3_geometry_obstacle_source_indices.clear();
  result.baseline_v3_boundary_warning_source_indices.clear();
  result.baseline_v3_model_assist_source_indices.clear();
  result.nearest_reportable_core = {};
}

void FinalizeReportableOutputs(const float* xyz, AnalysisResult& result) {
  auto sort_unique = [](std::vector<std::size_t>& values) {
    std::sort(values.begin(), values.end());
    values.erase(std::unique(values.begin(), values.end()), values.end());
  };
  sort_unique(result.reportable_core_source_indices);
  sort_unique(result.ignored_noise_source_indices);
  sort_unique(result.baseline_v3_geometry_obstacle_source_indices);
  sort_unique(result.baseline_v3_boundary_warning_source_indices);
  sort_unique(result.baseline_v3_model_assist_source_indices);
  result.reportable_core_count = result.reportable_core_source_indices.size();
  result.ignored_noise_count = result.ignored_noise_source_indices.size();
  result.baseline_v3_geometry_obstacle_count =
      result.baseline_v3_geometry_obstacle_source_indices.size();
  result.baseline_v3_boundary_warning_count =
      result.baseline_v3_boundary_warning_source_indices.size();
  result.baseline_v3_model_assist_count =
      result.baseline_v3_model_assist_source_indices.size();
  result.nearest_reportable_core = {};
  for (const std::size_t source_index : result.reportable_core_source_indices) {
    const double distance = std::hypot(static_cast<double>(xyz[source_index * 3]),
                                      xyz[source_index * 3 + 1], xyz[source_index * 3 + 2]);
    if (distance < result.nearest_reportable_core.distance_from_source_origin_m) {
      result.nearest_reportable_core.source_index = source_index;
      result.nearest_reportable_core.distance_from_source_origin_m = distance;
    }
  }
}

Point3f RailPairCentre(const RailPair& pair) {
  return Point3f{static_cast<float>((pair.left.x + pair.right.x) * 0.5),
                 static_cast<float>((pair.left.y + pair.right.y) * 0.5),
                 static_cast<float>((pair.left.z + pair.right.z) * 0.5)};
}

ArcGeometry EstimateLastThreeArc(const std::vector<RailPair>& pairs) {
  if (pairs.size() < 3) return {};
  const auto& last = pairs.back();
  const auto& before = pairs[pairs.size() - 2];
  const auto& first = pairs[pairs.size() - 3];
  const Point3f a = RailPairCentre(first);
  const Point3f b = RailPairCentre(before);
  const Point3f c = RailPairCentre(last);
  const double determinant = 2.0 * (static_cast<double>(a.x) * (b.y - c.y) +
                                    static_cast<double>(b.x) * (c.y - a.y) +
                                    static_cast<double>(c.x) * (a.y - b.y));
  if (std::abs(determinant) <= kTolerance) return {};
  const auto squared_norm = [](const Point3f& point) {
    return static_cast<double>(point.x) * point.x + static_cast<double>(point.y) * point.y;
  };
  const double a2 = squared_norm(a), b2 = squared_norm(b), c2 = squared_norm(c);
  const double centre_x = (a2 * (b.y - c.y) + b2 * (c.y - a.y) + c2 * (a.y - b.y)) / determinant;
  const double centre_y = (a2 * (c.x - b.x) + b2 * (a.x - c.x) + c2 * (b.x - a.x)) / determinant;
  const double radial_x = static_cast<double>(c.x) - centre_x;
  const double radial_y = static_cast<double>(c.y) - centre_y;
  const double radius = std::hypot(radial_x, radial_y);
  if (!std::isfinite(radius) || radius <= kTolerance) return {};
  const double motion_x = static_cast<double>(c.x) - b.x;
  const double motion_y = static_cast<double>(c.y) - b.y;
  const double ccw_x = -radial_y, ccw_y = radial_x;
  const double direction = (ccw_x * motion_x + ccw_y * motion_y >= 0.0) ? 1.0 : -1.0;
  const double station_step = last.source_s_m - before.source_s_m;
  if (station_step <= kTolerance) throw std::invalid_argument("last observed arc stations must differ");
  return {true, centre_x, centre_y, radius, direction, station_step};
}

bool Solve3x3(double matrix[3][4], double solution[3]) {
  for (int column = 0; column < 3; ++column) {
    int pivot = column;
    for (int row = column + 1; row < 3; ++row)
      if (std::abs(matrix[row][column]) > std::abs(matrix[pivot][column])) pivot = row;
    if (std::abs(matrix[pivot][column]) <= kTolerance) return false;
    if (pivot != column)
      for (int item = column; item < 4; ++item) std::swap(matrix[column][item], matrix[pivot][item]);
    const double divisor = matrix[column][column];
    for (int item = column; item < 4; ++item) matrix[column][item] /= divisor;
    for (int row = 0; row < 3; ++row) {
      if (row == column) continue;
      const double factor = matrix[row][column];
      for (int item = column; item < 4; ++item) matrix[row][item] -= factor * matrix[column][item];
    }
  }
  for (int index = 0; index < 3; ++index) solution[index] = matrix[index][3];
  return true;
}

ArcGeometry EstimateWindowArc(const std::vector<RailPair>& pairs, std::size_t fit_window_pairs) {
  if (pairs.size() < 3 || fit_window_pairs < 3) return {};
  const std::size_t count = std::min(fit_window_pairs, pairs.size());
  const std::size_t begin = pairs.size() - count;
  double normal[3][4]{};
  for (std::size_t index = begin; index < pairs.size(); ++index) {
    const Point3f point = RailPairCentre(pairs[index]);
    const double row[3]{static_cast<double>(point.x), static_cast<double>(point.y), 1.0};
    const double rhs = -(row[0] * row[0] + row[1] * row[1]);
    for (int r = 0; r < 3; ++r) {
      for (int c = 0; c < 3; ++c) normal[r][c] += row[r] * row[c];
      normal[r][3] += row[r] * rhs;
    }
  }
  double solution[3]{};
  if (!Solve3x3(normal, solution)) return {};
  const double centre_x = -solution[0] * 0.5;
  const double centre_y = -solution[1] * 0.5;
  const double radius2 = centre_x * centre_x + centre_y * centre_y - solution[2];
  if (!std::isfinite(radius2) || radius2 <= kTolerance) return {};
  const double radius = std::sqrt(radius2);
  const auto& last = pairs.back();
  const auto& before = pairs[pairs.size() - 2];
  const Point3f c = RailPairCentre(last);
  const Point3f b = RailPairCentre(before);
  const double radial_x = static_cast<double>(c.x) - centre_x;
  const double radial_y = static_cast<double>(c.y) - centre_y;
  if (std::hypot(radial_x, radial_y) <= kTolerance) return {};
  const double motion_x = static_cast<double>(c.x) - b.x;
  const double motion_y = static_cast<double>(c.y) - b.y;
  const double ccw_x = -radial_y, ccw_y = radial_x;
  const double direction = (ccw_x * motion_x + ccw_y * motion_y >= 0.0) ? 1.0 : -1.0;
  const double station_step = last.source_s_m - before.source_s_m;
  if (station_step <= kTolerance) throw std::invalid_argument("last observed arc stations must differ");
  return {true, centre_x, centre_y, radius, direction, station_step};
}

void AppendArcSamples(ArcLimitedExtensionResult& result, const ArcGeometry& arc,
                      double horizon_m) {
  if (horizon_m <= kTolerance) return;
  const auto before = result.rail_pairs[result.rail_pairs.size() - 2];
  const auto last = result.rail_pairs.back();
  result.applied_horizon_m = horizon_m;
  result.sample_step_m = std::min(arc.station_step_m, result.applied_horizon_m);
  const std::size_t samples = static_cast<std::size_t>(
      std::ceil(result.applied_horizon_m / result.sample_step_m));
  const auto rotate = [&arc](const Point3f& point, double angle, double z) {
    const double dx = static_cast<double>(point.x) - arc.centre_x;
    const double dy = static_cast<double>(point.y) - arc.centre_y;
    const double cosine = std::cos(angle), sine = std::sin(angle);
    return Point3f{static_cast<float>(arc.centre_x + cosine * dx - sine * dy),
                   static_cast<float>(arc.centre_y + sine * dx + cosine * dy),
                   static_cast<float>(z)};
  };
  for (std::size_t index = 1; index <= samples; ++index) {
    const double distance = std::min(result.applied_horizon_m, index * result.sample_step_m);
    const double scale = distance / arc.station_step_m;
    const double angle = arc.direction * distance / arc.radius_m;
    result.rail_pairs.push_back({last.source_s_m + distance,
                                 rotate(last.left, angle, last.left.z + (last.left.z - before.left.z) * scale),
                                 rotate(last.right, angle, last.right.z + (last.right.z - before.right.z) * scale)});
  }
  result.applied_turn_deg = result.applied_horizon_m / arc.radius_m * 180.0 / kPi;
}

}  // namespace

std::vector<RailPair> ValidateRailPairs(const std::vector<RailPair>& pairs) {
  if (pairs.size() < 2) throw std::invalid_argument("at least two rail pairs are required");
  std::vector<RailPair> normalized = pairs;
  for (std::size_t index = 0; index < normalized.size(); ++index) {
    const auto& pair = normalized[index];
    if (!std::isfinite(pair.source_s_m) || !IsFinite(pair.left) || !IsFinite(pair.right))
      throw std::invalid_argument("rail pairs must be finite");
    if (index && pair.source_s_m <= normalized[index - 1].source_s_m)
      throw std::invalid_argument("rail pairs must be strictly ordered");
    if (std::hypot(static_cast<double>(pair.left.x) - pair.right.x,
                   static_cast<double>(pair.left.y) - pair.right.y) < kTolerance)
      throw std::invalid_argument("rail pair sides must differ");
  }
  BuildSegments(normalized);
  return normalized;
}

std::vector<RailPair> ExtendRailPairsForward(const std::vector<RailPair>& pairs,
                                             double target_source_s_m) {
  auto normalized = ValidateRailPairs(pairs);
  if (!std::isfinite(target_source_s_m))
    throw std::invalid_argument("extrapolation target must be finite");
  const auto& before = normalized[normalized.size() - 2];
  const auto& last = normalized.back();
  if (target_source_s_m <= last.source_s_m + kTolerance) return normalized;
  const double source_delta = last.source_s_m - before.source_s_m;
  if (source_delta <= kTolerance)
    throw std::invalid_argument("last observed rail-pair stations must differ");
  const double scale = (target_source_s_m - last.source_s_m) / source_delta;
  const Point3f before_centre = RailPairCentre(before);
  const Point3f last_centre = RailPairCentre(last);
  const auto translate = [scale, &before_centre, &last_centre](const Point3f& point) {
    return Point3f{
        static_cast<float>(point.x + (static_cast<double>(last_centre.x) - before_centre.x) * scale),
        static_cast<float>(point.y + (static_cast<double>(last_centre.y) - before_centre.y) * scale),
        static_cast<float>(point.z + (static_cast<double>(last_centre.z) - before_centre.z) * scale),
    };
  };
  normalized.push_back({target_source_s_m,
                        translate(last.left),
                        translate(last.right)});
  BuildSegments(normalized);
  return normalized;
}

const char* ArcLimitedExtensionStatusName(ArcLimitedExtensionStatus status) {
  switch (status) {
    case ArcLimitedExtensionStatus::kApplied: return "ARC_LIMITED_APPLIED";
    case ArcLimitedExtensionStatus::kHorizonDisabled: return "ARC_HORIZON_DISABLED";
    case ArcLimitedExtensionStatus::kAtForwardLimit: return "AT_FORWARD_LIMIT";
    case ArcLimitedExtensionStatus::kInsufficientObservedPairs: return "INSUFFICIENT_ARC_SUPPORT";
    case ArcLimitedExtensionStatus::kCollinearObservedCenters: return "COLLINEAR_ARC_SUPPORT";
    case ArcLimitedExtensionStatus::kClampedApplied: return "ARC_CLAMPED_APPLIED";
    case ArcLimitedExtensionStatus::kClampedToMaxTurn: return "ARC_CLAMPED_TO_MAX_TURN";
    case ArcLimitedExtensionStatus::kClampedRejected: return "ARC_CLAMPED_REJECTED";
  }
  throw std::invalid_argument("unknown arc limited extension status");
}

ArcLimitedExtensionResult ExtendRailPairsForwardArcLimited(
    const std::vector<RailPair>& pairs, double requested_horizon_m,
    double max_source_s_m) {
  ArcLimitedExtensionResult result;
  result.rail_pairs = ValidateRailPairs(pairs);
  if (!std::isfinite(requested_horizon_m) || requested_horizon_m < 0.0 ||
      !std::isfinite(max_source_s_m)) {
    throw std::invalid_argument("arc extension horizon and limit must be finite and nonnegative");
  }
  if (requested_horizon_m <= kTolerance) return result;

  const auto& last = result.rail_pairs.back();
  const double available_horizon = max_source_s_m - last.source_s_m;
  if (available_horizon <= kTolerance) {
    result.status = ArcLimitedExtensionStatus::kAtForwardLimit;
    return result;
  }
  if (result.rail_pairs.size() < 3) {
    result.status = ArcLimitedExtensionStatus::kInsufficientObservedPairs;
    return result;
  }

  const auto arc = EstimateLastThreeArc(result.rail_pairs);
  if (!arc.valid) {
    result.status = ArcLimitedExtensionStatus::kCollinearObservedCenters;
    return result;
  }
  result.estimated_radius_m = arc.radius_m;
  result.applied_horizon_m = std::min(requested_horizon_m, available_horizon);
  result.requested_turn_deg = result.applied_horizon_m / arc.radius_m * 180.0 / kPi;
  AppendArcSamples(result, arc, result.applied_horizon_m);
  BuildSegments(result.rail_pairs);
  result.status = ArcLimitedExtensionStatus::kApplied;
  return result;
}

ArcLimitedExtensionResult ExtendRailPairsForwardArcClamped(
    const std::vector<RailPair>& pairs, double requested_horizon_m,
    double max_source_s_m, double min_radius_m, double max_turn_deg,
    std::size_t fit_window_pairs) {
  ArcLimitedExtensionResult result;
  result.rail_pairs = ValidateRailPairs(pairs);
  if (!std::isfinite(requested_horizon_m) || requested_horizon_m < 0.0 ||
      !std::isfinite(max_source_s_m) || !std::isfinite(min_radius_m) ||
      min_radius_m <= 0.0 || !std::isfinite(max_turn_deg) || max_turn_deg <= 0.0 ||
      fit_window_pairs < 3) {
    throw std::invalid_argument("arc clamp parameters must be finite positive values");
  }
  result.fit_window_pairs = std::min(fit_window_pairs, result.rail_pairs.size());
  if (requested_horizon_m <= kTolerance) return result;

  const auto& last = result.rail_pairs.back();
  const double available_horizon = max_source_s_m - last.source_s_m;
  if (available_horizon <= kTolerance) {
    result.status = ArcLimitedExtensionStatus::kAtForwardLimit;
    return result;
  }
  const double requested_available_horizon = std::min(requested_horizon_m, available_horizon);
  const auto reject_arc = [&]() {
    result.status = ArcLimitedExtensionStatus::kClampedRejected;
    return result;
  };
  if (result.rail_pairs.size() < 3) return reject_arc();

  const auto arc = EstimateWindowArc(result.rail_pairs, fit_window_pairs);
  if (!arc.valid) return reject_arc();
  result.estimated_radius_m = arc.radius_m;
  result.requested_turn_deg = requested_available_horizon / arc.radius_m * 180.0 / kPi;
  if (arc.radius_m < min_radius_m) return reject_arc();

  const double max_turn_rad = max_turn_deg * kPi / 180.0;
  const double max_turn_horizon = arc.radius_m * max_turn_rad;
  const double clamped_horizon = std::min(requested_available_horizon, max_turn_horizon);
  if (clamped_horizon <= kTolerance) return reject_arc();
  AppendArcSamples(result, arc, clamped_horizon);
  BuildSegments(result.rail_pairs);
  result.status = clamped_horizon + kTolerance < requested_available_horizon
      ? ArcLimitedExtensionStatus::kClampedToMaxTurn
      : ArcLimitedExtensionStatus::kClampedApplied;
  return result;
}

std::array<double, 8> CandidateBaselineV2Features(
    const float* xyz, const std::vector<std::size_t>& component) {
  const auto stats = ComputeComponentShapeStats(xyz, component);
  const double point_count = static_cast<double>(stats.point_count);
  const double extent_x = stats.max_x - stats.min_x;
  const double extent_y = stats.max_y - stats.min_y;
  const double extent_z = stats.max_z - stats.min_z;
  const double volume = std::max(extent_x * extent_y * extent_z, 1e-6);
  return {
      point_count,
      extent_x,
      extent_y,
      extent_z,
      volume,
      point_count / volume,
      std::hypot(stats.centroid_x, stats.centroid_y, stats.centroid_z),
      stats.nearest_distance_m,
  };
}

#include "candidate_baseline_v2_model.inc"

AnalysisResult AnalyzeCurveEnvelope(const float* xyz, std::size_t point_count,
                                    const std::vector<RailPair>& pairs,
                                    const Bounds& core, const Bounds& expanded,
                                    const CoreNoiseFilterConfig& noise_config) {
  if (!xyz) throw std::invalid_argument("xyz must not be null");
  if (!(core.left < core.right && core.bottom < core.top &&
        expanded.left <= core.left && expanded.right >= core.right &&
        expanded.bottom <= core.bottom && expanded.top >= core.top))
    throw std::invalid_argument("invalid envelope bounds");
  const auto normalized = pairs.empty() ? std::vector<RailPair>{} : ValidateRailPairs(pairs);
  const auto segments = BuildSegments(normalized);
  AnalysisResult result;
  result.labels.resize(point_count, Zone::kUnknown);
  for (std::size_t index = 0; index < point_count; ++index) {
    const Point3f point{xyz[index * 3], xyz[index * 3 + 1], xyz[index * 3 + 2]};
    if (!IsFinite(point)) throw std::invalid_argument("xyz must be finite");
    Zone first_margin_or_outside = Zone::kUnknown;
    for (const auto& segment : segments) {
      const double dx = static_cast<double>(point.x) - segment.a.x;
      const double dy = static_cast<double>(point.y) - segment.a.y;
      const double station = dx * segment.tx + dy * segment.ty;
      if (station < -kTolerance || station > segment.length + kTolerance) continue;
      const double lateral = dx * segment.nx + dy * segment.ny;
      const double height = static_cast<double>(point.z) - segment.a.z - segment.dz * station / segment.length;
      if (InBounds(core, lateral, height)) {
        first_margin_or_outside = Zone::kCore;
        break;
      }
      if (first_margin_or_outside == Zone::kUnknown && InBounds(expanded, lateral, height))
        first_margin_or_outside = Zone::kMargin;
      else if (first_margin_or_outside == Zone::kUnknown)
        first_margin_or_outside = Zone::kOutsideReference;
    }
    const Zone zone = first_margin_or_outside;
    result.labels[index] = zone;
    switch (zone) {
      case Zone::kCore: ++result.core_count; break;
      case Zone::kMargin: ++result.margin_count; break;
      case Zone::kOutsideReference: ++result.outside_reference_count; break;
      case Zone::kUnknown: ++result.unknown_count; break;
    }
    if (zone != Zone::kCore && zone != Zone::kMargin) continue;
    const double distance = std::hypot(static_cast<double>(point.x), point.y, point.z);
    NearestPoint* nearest = zone == Zone::kCore ? &result.nearest_core : &result.nearest_margin;
    if (distance < nearest->distance_from_source_origin_m) {
      nearest->source_index = index;
      nearest->distance_from_source_origin_m = distance;
    }
  }
  if (noise_config.enabled) ApplyCoreNoiseFilter(xyz, point_count, result, normalized, noise_config);
  return result;
}

void ApplyCoreNoiseFilter(const float* xyz, std::size_t point_count,
                          AnalysisResult& result,
                          const std::vector<RailPair>& pairs,
                          const CoreNoiseFilterConfig& config) {
  if (!xyz) throw std::invalid_argument("xyz must not be null");
  if (result.labels.size() != point_count)
    throw std::invalid_argument("labels must match point count");
  if (!config.enabled) {
    ResetReportableOutputs(result);
    return;
  }
  if (config.min_reportable_core_points == 0 || !std::isfinite(config.connectivity_radius_m) ||
      config.connectivity_radius_m <= 0.0 ||
      !std::isfinite(config.max_axis_span_m) || config.max_axis_span_m <= 0.0 ||
      !std::isfinite(config.max_average_axis_distance_m) || config.max_average_axis_distance_m <= 0.0)
    throw std::invalid_argument("invalid core noise filter config");

  ResetReportableOutputs(result);

  std::vector<std::size_t> core_indices;
  core_indices.reserve(result.core_count);
  for (std::size_t index = 0; index < result.labels.size(); ++index)
    if (result.labels[index] == Zone::kCore) core_indices.push_back(index);

  const auto segments = pairs.empty() ? std::vector<Segment>{} : BuildSegments(ValidateRailPairs(pairs));
  const double radius2 = config.connectivity_radius_m * config.connectivity_radius_m;
  std::vector<bool> visited(core_indices.size(), false);
  std::vector<std::size_t> stack;
  std::vector<std::size_t> component;
  for (std::size_t seed = 0; seed < core_indices.size(); ++seed) {
    if (visited[seed]) continue;
    visited[seed] = true;
    stack.assign(1, seed);
    component.clear();
    while (!stack.empty()) {
      const std::size_t local = stack.back();
      stack.pop_back();
      const std::size_t source_index = core_indices[local];
      component.push_back(source_index);
      const Point3f point{xyz[source_index * 3], xyz[source_index * 3 + 1], xyz[source_index * 3 + 2]};
      if (!IsFinite(point)) throw std::invalid_argument("xyz must be finite");
      for (std::size_t other = 0; other < core_indices.size(); ++other) {
        if (visited[other]) continue;
        const std::size_t other_source_index = core_indices[other];
        const Point3f candidate{xyz[other_source_index * 3], xyz[other_source_index * 3 + 1],
                                xyz[other_source_index * 3 + 2]};
        if (!IsFinite(candidate)) throw std::invalid_argument("xyz must be finite");
        const double dx = static_cast<double>(point.x) - candidate.x;
        const double dy = static_cast<double>(point.y) - candidate.y;
        const double dz = static_cast<double>(point.z) - candidate.z;
        if (dx * dx + dy * dy + dz * dz > radius2) continue;
        visited[other] = true;
        stack.push_back(other);
      }
    }

    const auto stats = ComputeComponentAxisStats(xyz, component, segments);
    const bool compact_enough =
        !stats.valid ||
        (stats.span_m <= config.max_axis_span_m &&
         stats.average_distance_m <= config.max_average_axis_distance_m);
    auto& target = component.size() >= config.min_reportable_core_points && compact_enough
                       ? result.reportable_core_source_indices
                       : result.ignored_noise_source_indices;
    target.insert(target.end(), component.begin(), component.end());
  }

  FinalizeReportableOutputs(xyz, result);
}

void ApplyCandidateBaselineV2(const float* xyz, std::size_t point_count,
                              AnalysisResult& result,
                              double connectivity_radius_m,
                              FrozenNoiseTreeV1Profile* profile) {
  if (!xyz) throw std::invalid_argument("xyz must not be null");
  if (result.labels.size() != point_count)
    throw std::invalid_argument("labels must match point count");
  if (!std::isfinite(connectivity_radius_m) || connectivity_radius_m <= 0.0)
    throw std::invalid_argument("invalid model connectivity radius");
  if (profile) *profile = {};
  const auto profile_started = std::chrono::steady_clock::now();

  ResetReportableOutputs(result);

  std::vector<std::size_t> core_indices;
  core_indices.reserve(result.core_count);
  for (std::size_t index = 0; index < result.labels.size(); ++index)
    if (result.labels[index] == Zone::kCore) core_indices.push_back(index);
  auto core_index_extracted = std::chrono::steady_clock::now();
  if (profile) {
    profile->core_index_count = core_indices.size();
    profile->core_index_extract_ms = std::chrono::duration<double, std::milli>(
        core_index_extracted - profile_started).count();
  }

  const double radius2 = connectivity_radius_m * connectivity_radius_m;
  const auto spatial_index = BuildSpatialIndex(xyz, core_indices, connectivity_radius_m);
  std::vector<bool> visited(core_indices.size(), false);
  std::vector<std::size_t> stack;
  std::vector<std::size_t> component;
  auto connected_components_started = core_index_extracted;
  double tree_decision_ms = 0.0;
  for (std::size_t seed = 0; seed < core_indices.size(); ++seed) {
    if (visited[seed]) continue;
    visited[seed] = true;
    stack.assign(1, seed);
    component.clear();
    while (!stack.empty()) {
      const std::size_t local = stack.back();
      stack.pop_back();
      const std::size_t source_index = core_indices[local];
      component.push_back(source_index);
      const Point3f point{xyz[source_index * 3], xyz[source_index * 3 + 1], xyz[source_index * 3 + 2]};
      if (!IsFinite(point)) throw std::invalid_argument("xyz must be finite");
      const SpatialCell cell = PointCell(point, connectivity_radius_m);
      for (int dz_cell = -1; dz_cell <= 1; ++dz_cell) {
        for (int dy_cell = -1; dy_cell <= 1; ++dy_cell) {
          for (int dx_cell = -1; dx_cell <= 1; ++dx_cell) {
            const auto nearby = spatial_index.find({
                cell.x + dx_cell, cell.y + dy_cell, cell.z + dz_cell});
            if (nearby == spatial_index.end()) continue;
            for (const std::size_t other : nearby->second) {
              if (visited[other]) continue;
              if (profile) ++profile->neighbor_distance_checks;
              const std::size_t other_source_index = core_indices[other];
              const Point3f candidate{xyz[other_source_index * 3], xyz[other_source_index * 3 + 1],
                                      xyz[other_source_index * 3 + 2]};
              const double dx = static_cast<double>(point.x) - candidate.x;
              const double dy = static_cast<double>(point.y) - candidate.y;
              const double dz = static_cast<double>(point.z) - candidate.z;
              if (dx * dx + dy * dy + dz * dz > radius2) continue;
              visited[other] = true;
              stack.push_back(other);
            }
          }
        }
      }
    }

    const auto tree_decision_started = std::chrono::steady_clock::now();
    const auto features = CandidateBaselineV2Features(xyz, component);
    const bool model_obstacle =
        CandidateBaselineV2Score(features) >= kCandidateBaselineV2Threshold;
    const auto tree_decision_finished = std::chrono::steady_clock::now();
    tree_decision_ms += std::chrono::duration<double, std::milli>(
        tree_decision_finished - tree_decision_started).count();
    if (profile) {
      ++profile->component_count;
      if (model_obstacle) ++profile->model_obstacle_component_count;
      else ++profile->model_noise_component_count;
    }
    auto& target = model_obstacle
                       ? result.reportable_core_source_indices
                       : result.ignored_noise_source_indices;
    target.insert(target.end(), component.begin(), component.end());
  }
  const auto connected_components_finished = std::chrono::steady_clock::now();
  if (profile) {
    profile->connected_components_and_features_ms =
        std::chrono::duration<double, std::milli>(
            connected_components_finished - connected_components_started).count() - tree_decision_ms;
    profile->tree_decision_ms = tree_decision_ms;
  }

  FinalizeReportableOutputs(xyz, result);
  if (profile) {
    profile->output_finalize_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - connected_components_finished).count();
  }
}

void ApplyBaselineV3(const float* xyz, std::size_t point_count,
                     AnalysisResult& result,
                     double connectivity_radius_m,
                     FrozenNoiseTreeV1Profile* profile) {
  if (!xyz) throw std::invalid_argument("xyz must not be null");
  if (result.labels.size() != point_count)
    throw std::invalid_argument("labels must match point count");
  if (!std::isfinite(connectivity_radius_m) || connectivity_radius_m <= 0.0)
    throw std::invalid_argument("invalid baseline_v3 connectivity radius");
  if (profile) *profile = {};
  const auto profile_started = std::chrono::steady_clock::now();

  ResetReportableOutputs(result);

  std::vector<std::size_t> core_indices;
  core_indices.reserve(result.core_count);
  for (std::size_t index = 0; index < result.labels.size(); ++index)
    if (result.labels[index] == Zone::kCore) core_indices.push_back(index);
  const auto core_index_extracted = std::chrono::steady_clock::now();
  if (profile) {
    profile->core_index_count = core_indices.size();
    profile->core_index_extract_ms = std::chrono::duration<double, std::milli>(
        core_index_extracted - profile_started).count();
  }

  constexpr std::size_t kStrongGeometryMinPoints = 1000;
  constexpr std::size_t kBoundaryWarningMinPoints = 250;
  const double radius2 = connectivity_radius_m * connectivity_radius_m;
  const auto spatial_index = BuildSpatialIndex(xyz, core_indices, connectivity_radius_m);
  std::vector<bool> visited(core_indices.size(), false);
  std::vector<std::size_t> stack;
  std::vector<std::size_t> component;
  const auto connected_components_started = core_index_extracted;
  double tree_decision_ms = 0.0;
  for (std::size_t seed = 0; seed < core_indices.size(); ++seed) {
    if (visited[seed]) continue;
    visited[seed] = true;
    stack.assign(1, seed);
    component.clear();
    while (!stack.empty()) {
      const std::size_t local = stack.back();
      stack.pop_back();
      const std::size_t source_index = core_indices[local];
      component.push_back(source_index);
      const Point3f point{xyz[source_index * 3], xyz[source_index * 3 + 1], xyz[source_index * 3 + 2]};
      if (!IsFinite(point)) throw std::invalid_argument("xyz must be finite");
      const SpatialCell cell = PointCell(point, connectivity_radius_m);
      for (int dz_cell = -1; dz_cell <= 1; ++dz_cell) {
        for (int dy_cell = -1; dy_cell <= 1; ++dy_cell) {
          for (int dx_cell = -1; dx_cell <= 1; ++dx_cell) {
            const auto nearby = spatial_index.find({
                cell.x + dx_cell, cell.y + dy_cell, cell.z + dz_cell});
            if (nearby == spatial_index.end()) continue;
            for (const std::size_t other : nearby->second) {
              if (visited[other]) continue;
              if (profile) ++profile->neighbor_distance_checks;
              const std::size_t other_source_index = core_indices[other];
              const Point3f candidate{xyz[other_source_index * 3], xyz[other_source_index * 3 + 1],
                                      xyz[other_source_index * 3 + 2]};
              const double dx = static_cast<double>(point.x) - candidate.x;
              const double dy = static_cast<double>(point.y) - candidate.y;
              const double dz = static_cast<double>(point.z) - candidate.z;
              if (dx * dx + dy * dy + dz * dz > radius2) continue;
              visited[other] = true;
              stack.push_back(other);
            }
          }
        }
      }
    }

    const auto shape = ComputeComponentShapeStats(xyz, component);
    const bool boundary_warning =
        component.size() >= kBoundaryWarningMinPoints && BaselineV3BoundaryWarning(shape);
    bool model_obstacle = false;
    if (!boundary_warning &&
        component.size() < kStrongGeometryMinPoints) {
      const auto tree_decision_started = std::chrono::steady_clock::now();
      const auto features = CandidateBaselineV2Features(xyz, component);
      model_obstacle = CandidateBaselineV2Score(features) >= kCandidateBaselineV2Threshold;
      const auto tree_decision_finished = std::chrono::steady_clock::now();
      tree_decision_ms += std::chrono::duration<double, std::milli>(
          tree_decision_finished - tree_decision_started).count();
    }
    if (profile) {
      ++profile->component_count;
      if ((component.size() >= kStrongGeometryMinPoints && !boundary_warning) || model_obstacle)
        ++profile->model_obstacle_component_count;
      else
        ++profile->model_noise_component_count;
    }

    if (boundary_warning) {
      result.baseline_v3_boundary_warning_source_indices.insert(
          result.baseline_v3_boundary_warning_source_indices.end(),
          component.begin(), component.end());
      result.ignored_noise_source_indices.insert(
          result.ignored_noise_source_indices.end(), component.begin(), component.end());
    } else if (component.size() >= kStrongGeometryMinPoints) {
      result.baseline_v3_geometry_obstacle_source_indices.insert(
          result.baseline_v3_geometry_obstacle_source_indices.end(),
          component.begin(), component.end());
      result.reportable_core_source_indices.insert(
          result.reportable_core_source_indices.end(), component.begin(), component.end());
    } else if (model_obstacle) {
      result.baseline_v3_model_assist_source_indices.insert(
          result.baseline_v3_model_assist_source_indices.end(),
          component.begin(), component.end());
      result.reportable_core_source_indices.insert(
          result.reportable_core_source_indices.end(), component.begin(), component.end());
    } else {
      result.ignored_noise_source_indices.insert(
          result.ignored_noise_source_indices.end(), component.begin(), component.end());
    }
  }
  const auto connected_components_finished = std::chrono::steady_clock::now();
  if (profile) {
    profile->connected_components_and_features_ms =
        std::chrono::duration<double, std::milli>(
            connected_components_finished - connected_components_started).count() - tree_decision_ms;
    profile->tree_decision_ms = tree_decision_ms;
  }
  FinalizeReportableOutputs(xyz, result);
  if (profile) {
    profile->output_finalize_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - connected_components_finished).count();
  }
}

std::vector<LineSegment3f> BuildCurveEnvelopeWireframe(
    const std::vector<RailPair>& pairs, const Bounds& bounds) {
  if (!ValidBounds(bounds)) throw std::invalid_argument("invalid wireframe bounds");
  if (pairs.empty()) return {};
  const auto segments = BuildSegments(ValidateRailPairs(pairs));
  constexpr std::array<std::array<std::size_t, 2>, 12> edges{{
      {{0, 1}}, {{1, 3}}, {{3, 2}}, {{2, 0}},
      {{4, 5}}, {{5, 7}}, {{7, 6}}, {{6, 4}},
      {{0, 4}}, {{1, 5}}, {{2, 6}}, {{3, 7}},
  }};
  std::vector<LineSegment3f> wireframe;
  wireframe.reserve(segments.size() * edges.size());
  for (const auto& segment : segments) {
    const std::array<Point3f, 8> corners{{
        SegmentPoint(segment, 0.0, bounds.left, bounds.bottom),
        SegmentPoint(segment, 0.0, bounds.left, bounds.top),
        SegmentPoint(segment, 0.0, bounds.right, bounds.bottom),
        SegmentPoint(segment, 0.0, bounds.right, bounds.top),
        SegmentPoint(segment, segment.length, bounds.left, bounds.bottom),
        SegmentPoint(segment, segment.length, bounds.left, bounds.top),
        SegmentPoint(segment, segment.length, bounds.right, bounds.bottom),
        SegmentPoint(segment, segment.length, bounds.right, bounds.top),
    }};
    for (const auto& edge : edges)
      wireframe.push_back({corners[edge[0]], corners[edge[1]]});
  }
  return wireframe;
}

std::string ZoneName(Zone zone) {
  switch (zone) {
    case Zone::kUnknown: return "UNKNOWN";
    case Zone::kCore: return "CORE";
    case Zone::kMargin: return "MARGIN";
    case Zone::kOutsideReference: return "OUTSIDE_REFERENCE";
  }
  throw std::invalid_argument("unknown zone");
}

}  // namespace lidar_mosmetro3d
