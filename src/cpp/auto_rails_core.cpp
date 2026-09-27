#include "auto_rails_core.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace lidar_mosmetro3d {
namespace {

struct Sample { double x; double s; double z; };
struct Peak { double s; double x; double z; double prominence; Point3f point; };
struct Pair { double s; double l; double r; double lz; double rz; Point3f left; Point3f right; };
struct Line { double slope; double intercept; };
struct Model { Line l; Line r; Line lz; Line rz; };
struct Candidate { Model model; std::vector<Pair> rows; double rms; };

double Quantile(std::vector<double> values, double q) {
  if (values.empty()) return std::numeric_limits<double>::quiet_NaN();
  std::sort(values.begin(), values.end());
  return values[static_cast<std::size_t>(std::floor((values.size() - 1) * q))];
}

Line Fit(const std::vector<Pair>& rows, double Pair::*field) {
  double mean_s = 0.0, mean_v = 0.0;
  for (const auto& row : rows) { mean_s += row.s; mean_v += row.*field; }
  mean_s /= rows.size(); mean_v /= rows.size();
  double denominator = 0.0, numerator = 0.0;
  for (const auto& row : rows) {
    denominator += (row.s - mean_s) * (row.s - mean_s);
    numerator += (row.s - mean_s) * (row.*field - mean_v);
  }
  const double slope = denominator == 0.0 ? 0.0 : numerator / denominator;
  return {slope, mean_v - slope * mean_s};
}

double Value(const Line& line, double station) { return line.intercept + line.slope * station; }
Model FitModel(const std::vector<Pair>& rows) {
  return {Fit(rows, &Pair::l), Fit(rows, &Pair::r), Fit(rows, &Pair::lz), Fit(rows, &Pair::rz)};
}

double Error(const Pair& pair, const Model& model, const AutoRailsConfig& c) {
  return std::max({std::abs(pair.l - Value(model.l, pair.s)) / c.lateral_tolerance,
                   std::abs(pair.r - Value(model.r, pair.s)) / c.lateral_tolerance,
                   std::abs(pair.lz - Value(model.lz, pair.s)) / c.height_tolerance,
                   std::abs(pair.rz - Value(model.rz, pair.s)) / c.height_tolerance});
}

std::vector<Peak> StationPeaks(const std::vector<Sample>& points, double station,
                               const AutoRailsConfig& c) {
  const int cell_count = static_cast<int>(std::ceil((c.lateral_max - c.lateral_min) / c.cell_width));
  std::vector<std::vector<Sample>> cells(cell_count);
  for (const auto& point : points) cells[static_cast<int>((point.x - c.lateral_min) / c.cell_width)].push_back(point);
  std::vector<double> floors;
  for (const auto& cell : cells) if (static_cast<int>(cell.size()) >= c.min_cell_points) {
    std::vector<double> z; z.reserve(cell.size()); for (const auto& point : cell) z.push_back(point.z);
    floors.push_back(Quantile(std::move(z), c.cell_floor_quantile));
  }
  const double floor = Quantile(std::move(floors), c.floor_quantile);
  for (auto& cell : cells) cell.erase(std::remove_if(cell.begin(), cell.end(), [&](const Sample& point) {
    return point.z < floor - c.floor_band_below || point.z > floor + c.floor_band_above;
  }), cell.end());
  std::vector<double> heights(cell_count, std::numeric_limits<double>::quiet_NaN());
  for (int i = 0; i < cell_count; ++i) if (static_cast<int>(cells[i].size()) >= c.min_cell_points) {
    std::vector<double> z; z.reserve(cells[i].size()); for (const auto& point : cells[i]) z.push_back(point.z);
    heights[i] = Quantile(std::move(z), c.head_quantile);
  }
  std::vector<Peak> peaks;
  const int first_flank = static_cast<int>(std::ceil(c.flank_min / c.cell_width));
  const int last_flank = static_cast<int>(std::floor(c.flank_max / c.cell_width));
  for (int i = 0; i < cell_count; ++i) {
    if (!std::isfinite(heights[i])) continue;
    std::vector<double> left, right;
    for (int j = first_flank; j <= last_flank; ++j) {
      if (i - j >= 0 && std::isfinite(heights[i - j])) left.push_back(heights[i - j]);
      if (i + j < cell_count && std::isfinite(heights[i + j])) right.push_back(heights[i + j]);
    }
    if (static_cast<int>(left.size()) < c.min_flank_cells || static_cast<int>(right.size()) < c.min_flank_cells) continue;
    const double prominence = std::min(heights[i] - Quantile(std::move(left), .5), heights[i] - Quantile(std::move(right), .5));
    if (prominence < c.min_prominence || prominence > c.max_prominence) continue;
    std::vector<Sample> near_head;
    for (const auto& point : cells[i]) if (point.z >= heights[i] - c.head_band) near_head.push_back(point);
    std::vector<double> xs; xs.reserve(near_head.size()); for (const auto& point : near_head) xs.push_back(point.x);
    const double x = Quantile(std::move(xs), .5);
    const auto observed = *std::min_element(near_head.begin(), near_head.end(), [&](const Sample& a, const Sample& b) {
      return std::abs(a.x - x) + std::abs(a.s - station) * .01 < std::abs(b.x - x) + std::abs(b.s - station) * .01;
    });
    peaks.push_back({station, x, heights[i], prominence, {static_cast<float>(observed.x), static_cast<float>(-observed.s), static_cast<float>(observed.z)}});
  }
  std::sort(peaks.begin(), peaks.end(), [](const Peak& a, const Peak& b) { return a.prominence > b.prominence; });
  std::vector<Peak> selected;
  for (const auto& peak : peaks) {
    bool separate = true; for (const auto& prior : selected) if (std::abs(peak.x - prior.x) <= c.peak_separation) separate = false;
    if (separate) selected.push_back(peak);
  }
  std::sort(selected.begin(), selected.end(), [](const Peak& a, const Peak& b) { return a.x < b.x; });
  return selected;
}

bool ValidConfig(const AutoRailsConfig& c) {
  return c.forward_max > c.forward_min && c.lateral_max > c.lateral_min && c.station_length > 0.0 && c.cell_width > 0.0 &&
         c.min_stations >= 3 && c.min_cell_points >= 1 && c.min_flank_cells >= 1 && c.min_span > 0.0 && c.max_gap > 0.0 &&
         c.pair_min > 0.0 && c.pair_max >= c.pair_min && c.lateral_tolerance > 0.0 && c.height_tolerance > 0.0 &&
         c.min_coverage > 0.0 && c.min_coverage <= 1.0 && c.ambiguity_ratio > 0.0 && c.ambiguity_ratio <= 1.0;
}

std::vector<RailPair> ToRailPairs(const std::vector<Pair>& pairs) {
  std::vector<RailPair> rails;
  rails.reserve(pairs.size());
  for (const auto& pair : pairs) rails.push_back({pair.s, pair.left, pair.right});
  return rails;
}

double CenterX(const Pair& pair) { return (pair.l + pair.r) * 0.5; }

double SharedStationLateralDisplacement(
    const std::vector<Pair>& selected_chain,
    const std::vector<Pair>& competing_chain,
    bool* has_shared_station) {
  double displacement = 0.0;
  *has_shared_station = false;
  for (const auto& selected : selected_chain) {
    for (const auto& competing : competing_chain) {
      if (std::abs(selected.s - competing.s) > 1e-6) continue;
      *has_shared_station = true;
      displacement = std::max(displacement, std::abs(CenterX(competing) - CenterX(selected)));
    }
  }
  return displacement;
}

}  // namespace

const char* RailSelectionMethodName(RailSelectionMethod method) {
  switch (method) {
    case RailSelectionMethod::kBaseline: return "baseline";
    case RailSelectionMethod::kDevelopmentCandidate: return "development_candidate";
  }
  return "invalid";
}

AutoRailsResult DetectAutoRails(const float* xyz, std::size_t point_count, const AutoRailsConfig& c,
                                RailSelectionMethod method) {
  AutoRailsResult result;
  if (!xyz || !ValidConfig(c)) { result.reason = "INVALID_SEARCH_PARAMETERS"; return result; }
  if (method != RailSelectionMethod::kBaseline && method != RailSelectionMethod::kDevelopmentCandidate) {
    result.reason = "INVALID_RAIL_SELECTION_METHOD";
    return result;
  }
  const int station_count = static_cast<int>(std::ceil((c.forward_max - c.forward_min) / c.station_length));
  std::vector<std::vector<Sample>> stations(station_count);
  for (std::size_t i = 0; i < point_count; ++i) {
    const double x = xyz[i * 3], s = -static_cast<double>(xyz[i * 3 + 1]), z = xyz[i * 3 + 2];
    if (!std::isfinite(x) || !std::isfinite(s) || !std::isfinite(z)) { result.reason = "NONFINITE_XYZ"; return result; }
    if (s >= c.forward_min && s < c.forward_max && x >= c.lateral_min && x < c.lateral_max)
      stations[static_cast<int>((s - c.forward_min) / c.station_length)].push_back({x, s, z});
  }
  std::vector<std::vector<Pair>> bins; bins.reserve(stations.size());
  for (int i = 0; i < station_count; ++i) {
    const auto peaks = StationPeaks(stations[i], c.forward_min + (i + .5) * c.station_length, c);
    std::vector<Pair> pairs;
    for (std::size_t a = 0; a < peaks.size(); ++a) for (std::size_t b = a + 1; b < peaks.size(); ++b) {
      const double width = peaks[b].x - peaks[a].x;
      if (width >= c.pair_min && width <= c.pair_max && std::abs(peaks[b].z - peaks[a].z) <= c.max_cross_height)
        pairs.push_back({peaks[a].s, peaks[a].x, peaks[b].x, peaks[a].z, peaks[b].z, peaks[a].point, peaks[b].point});
    }
    bins.push_back(std::move(pairs));
  }
  result.station_count = station_count;
  for (const auto& bin : bins) if (!bin.empty()) ++result.pair_stations;
  if (result.pair_stations < c.min_stations) { result.reason = "INSUFFICIENT_PAIRED_RAIL_SUPPORT"; return result; }
  if (method == RailSelectionMethod::kDevelopmentCandidate) {
    // Dynamic programming considers only observed pairs in increasing station
    // order. The returned chain ends at its last observed pair: no tangent,
    // spline, or temporal extrapolation is produced here.
    for (const auto& bin : bins) if (static_cast<int>(bin.size()) > c.max_pairs_per_station) {
      result.reason = "SEARCH_BUDGET_EXCEEDED";
      return result;
    }
    struct LocalNode { Pair pair; int score = 1; double cost = 0.0; int previous = -1; };
    std::vector<LocalNode> nodes;
    for (const auto& bin : bins) for (const auto& pair : bin) nodes.push_back({pair});
    for (std::size_t current = 0; current < nodes.size(); ++current) {
      for (std::size_t previous = 0; previous < current; ++previous) {
        const auto& a = nodes[previous].pair;
        const auto& b = nodes[current].pair;
        const double gap = b.s - a.s;
        if (gap <= 0.0 || gap > c.max_gap) continue;
        const double per_m = std::max({std::abs(b.l - a.l) / gap, std::abs(b.r - a.r) / gap,
                                       std::abs(b.lz - a.lz) / gap, std::abs(b.rz - a.rz) / gap});
        if (per_m > c.max_slope) continue;
        const double edge_cost = per_m / c.max_slope + (gap - c.station_length) / c.station_length;
        const int score = nodes[previous].score + 1;
        const double cost = nodes[previous].cost + edge_cost;
        if (score > nodes[current].score || (score == nodes[current].score && cost < nodes[current].cost)) {
          nodes[current].score = score;
          nodes[current].cost = cost;
          nodes[current].previous = static_cast<int>(previous);
        }
      }
    }
    int best = -1;
    for (std::size_t index = 0; index < nodes.size(); ++index) {
      if (nodes[index].score < c.min_stations) continue;
      if (best < 0 || nodes[index].score > nodes[best].score ||
          (nodes[index].score == nodes[best].score && nodes[index].cost < nodes[best].cost)) best = static_cast<int>(index);
    }
    if (best < 0) {
      result.reason = nodes.empty() ? "INSUFFICIENT_PAIRED_RAIL_SUPPORT" : "INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT";
      return result;
    }
    std::vector<Pair> chain;
    for (int index = best; index >= 0; index = nodes[index].previous) chain.push_back(nodes[index].pair);
    std::reverse(chain.begin(), chain.end());
    const double span = chain.back().s - chain.front().s;
    const double coverage = chain.size() / (span / c.station_length + 1.0);
    result.supported_stations = static_cast<int>(chain.size());
    result.best_path_score = nodes[best].score;
    result.best_path_cost = nodes[best].cost;
    result.best_path_span_m = span;
    result.best_path_coverage = coverage;
    result.best_path_start_s_m = chain.front().s;
    result.best_path_end_s_m = chain.back().s;
    result.best_path_pairs = ToRailPairs(chain);
    if (span < c.min_span || coverage < c.min_coverage) {
      result.reason = "INSUFFICIENT_CONTIGUOUS_COVERAGE";
      return result;
    }
    for (std::size_t index = 0; index < nodes.size(); ++index) {
      if (static_cast<int>(index) == best || nodes[index].score < nodes[best].score * c.ambiguity_ratio) continue;
      const auto& alternative = nodes[index].pair;
      const auto& selected = nodes[best].pair;
      std::vector<Pair> competing_chain;
      for (int alternative_index = static_cast<int>(index); alternative_index >= 0;
           alternative_index = nodes[alternative_index].previous) {
        competing_chain.push_back(nodes[alternative_index].pair);
      }
      std::reverse(competing_chain.begin(), competing_chain.end());
      bool has_shared_station = false;
      double lateral_displacement = SharedStationLateralDisplacement(
          chain, competing_chain, &has_shared_station);
      if (!has_shared_station) {
        lateral_displacement = std::abs(CenterX(alternative) - CenterX(selected));
      }
      if (lateral_displacement <= c.pair_min * .5) continue;
      result.competing_path_score = nodes[index].score;
      result.competing_path_cost = nodes[index].cost;
      result.competing_path_lateral_displacement_m = lateral_displacement;
      result.competing_path_end_s_m = alternative.s;
      result.competing_path_pairs = ToRailPairs(competing_chain);
      result.reason = "AMBIGUOUS_LOCAL_CONTINUITY_PATH";
      return result;
    }
    result.status = "AUTO_HYPOTHESIS";
    result.reason = "PAIRED_RAISED_LOCAL_CONTINUITY_PATH";
    result.rail_pairs = result.best_path_pairs;
    return result;
  }
  int seeds = 0;
  for (int i = 0; i < station_count; ++i) for (int j = i + 1; j < station_count; ++j)
    if ((j - i) * c.station_length >= c.min_span) seeds += static_cast<int>(bins[i].size() * bins[j].size());
  for (const auto& bin : bins) if (static_cast<int>(bin.size()) > c.max_pairs_per_station) { result.reason = "SEARCH_BUDGET_EXCEEDED"; return result; }
  if (seeds > c.max_seed_pairs) { result.reason = "SEARCH_BUDGET_EXCEEDED"; return result; }
  std::vector<Candidate> candidates;
  const auto gather = [&](const Model& model) {
    std::vector<Pair> rows;
    for (const auto& bin : bins) {
      const Pair* best = nullptr; double best_error = std::numeric_limits<double>::infinity();
      for (const auto& pair : bin) { const double error = Error(pair, model, c); if (error <= 1.0 && error < best_error) { best = &pair; best_error = error; } }
      if (best) rows.push_back(*best);
    }
    return rows;
  };
  for (int i = 0; i < station_count; ++i) for (int j = i + 1; j < station_count; ++j) {
    if ((j - i) * c.station_length < c.min_span) continue;
    for (const auto& a : bins[i]) for (const auto& b : bins[j]) {
      Model model = FitModel({a, b});
      if (std::max({std::abs(model.l.slope), std::abs(model.r.slope), std::abs(model.lz.slope), std::abs(model.rz.slope)}) > c.max_slope) continue;
      auto rows = gather(model); if (static_cast<int>(rows.size()) < c.min_stations) continue;
      model = FitModel(rows); rows = gather(model); if (static_cast<int>(rows.size()) < c.min_stations) continue;
      std::vector<std::vector<Pair>> runs(1);
      for (const auto& row : rows) { if (!runs.back().empty() && row.s - runs.back().back().s > c.max_gap) runs.emplace_back(); runs.back().push_back(row); }
      for (const auto& run : runs) {
        const double span = run.empty() ? 0.0 : run.back().s - run.front().s;
        if (static_cast<int>(run.size()) < c.min_stations || span < c.min_span || run.size() / (span / c.station_length + 1.0) < c.min_coverage) continue;
        model = FitModel(run);
        const double center_slope = (model.l.slope + model.r.slope) * .5;
        if (std::abs(model.l.slope - model.r.slope) * span > c.lateral_tolerance ||
            std::max({std::abs(model.l.slope), std::abs(model.r.slope), std::abs(model.lz.slope), std::abs(model.rz.slope)}) > c.max_slope) continue;
        if (std::any_of(run.begin(), run.end(), [&](const Pair& row) { return Error(row, model, c) > 1.0; })) continue;
        double squared = 0.0; for (const auto& row : run) for (const double diff : {row.l - Value(model.l,row.s), row.r - Value(model.r,row.s), row.lz - Value(model.lz,row.s), row.rz - Value(model.rz,row.s)}) squared += diff * diff;
        const double rms = std::sqrt(squared / (run.size() * 4));
        if (rms > c.max_rms) continue;
        bool invalid = false; for (const double station : {run.front().s, run.back().s}) {
          const double width = (Value(model.r,station) - Value(model.l,station)) / std::hypot(1.0, center_slope);
          if (width < c.pair_min || width > c.pair_max || std::abs(Value(model.rz,station) - Value(model.lz,station)) > c.max_cross_height) invalid = true;
        }
        if (!invalid) candidates.push_back({model, run, rms});
      }
    }
  }
  if (candidates.empty()) { result.reason = "NO_STRAIGHT_CONSISTENT_PAIR"; return result; }
  std::sort(candidates.begin(), candidates.end(), [](const Candidate& a, const Candidate& b) {
    return a.rows.size() != b.rows.size() ? a.rows.size() > b.rows.size() : a.rms < b.rms;
  });
  const auto& best = candidates.front();
  const double start = best.rows.front().s, end = best.rows.back().s;
  for (const auto& candidate : candidates) if (candidate.rows.size() >= best.rows.size() * c.ambiguity_ratio) {
    const auto displacement = std::max({std::abs(Value(candidate.model.l,start) - Value(best.model.l,start)), std::abs(Value(candidate.model.r,start) - Value(best.model.r,start)),
                                        std::abs(Value(candidate.model.l,end) - Value(best.model.l,end)), std::abs(Value(candidate.model.r,end) - Value(best.model.r,end))});
    if (displacement > c.pair_min / 2.0) { result.reason = "AMBIGUOUS_RAIL_PAIRS"; return result; }
  }
  result.status = "AUTO_HYPOTHESIS"; result.reason = "PAIRED_RAISED_LINEAR_RIDGES";
  result.supported_stations = static_cast<int>(best.rows.size()); result.rms = best.rms;
  result.rail_pairs.reserve(best.rows.size());
  for (const auto& row : best.rows) result.rail_pairs.push_back({row.s, row.left, row.right});
  return result;
}

}  // namespace lidar_mosmetro3d
