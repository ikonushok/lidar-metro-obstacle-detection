#include "auto_rails_core.hpp"
#include "cuda_envelope.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using lidar_mosmetro3d::AnalysisResult;
using lidar_mosmetro3d::AutoRailsResult;
using lidar_mosmetro3d::Bounds;

std::vector<float> ReadXyzf(const std::string& path) {
  std::ifstream stream(path, std::ios::binary | std::ios::ate);
  if (!stream) throw std::runtime_error("cannot open xyzf");
  const auto bytes = stream.tellg();
  if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(float) * 3) != 0) throw std::runtime_error("invalid xyzf");
  std::vector<float> xyz(static_cast<std::size_t>(bytes) / sizeof(float));
  stream.seekg(0); stream.read(reinterpret_cast<char*>(xyz.data()), bytes);
  if (!stream) throw std::runtime_error("cannot read xyzf");
  return xyz;
}

struct PipelineResult {
  AutoRailsResult rails;
  AnalysisResult envelope;
};

PipelineResult Run(const std::vector<float>& xyz, const Bounds& core, const Bounds& margin) {
  PipelineResult result;
  result.rails = lidar_mosmetro3d::DetectAutoRails(xyz.data(), xyz.size() / 3);
  if (result.rails.rail_pairs.size() < 2) {
    result.envelope = lidar_mosmetro3d::AnalyzeCurveEnvelope(xyz.data(), xyz.size() / 3, {}, core, margin);
    return result;
  }
  result.envelope = lidar_mosmetro3d::AnalyzeCurveEnvelopeCuda(
      xyz.data(), xyz.size() / 3, result.rails.rail_pairs, core, margin);
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 11) {
    std::cerr << "usage: cuda_pipeline_cli XYZF core_left core_right core_bottom core_top margin_left margin_right margin_bottom margin_top repetitions\n";
    return 2;
  }
  try {
    const auto xyz = ReadXyzf(argv[1]);
    const Bounds core{std::stod(argv[2]), std::stod(argv[3]), std::stod(argv[4]), std::stod(argv[5])};
    const Bounds margin{std::stod(argv[6]), std::stod(argv[7]), std::stod(argv[8]), std::stod(argv[9])};
    const int repetitions = std::stoi(argv[10]);
    if (repetitions < 1) throw std::runtime_error("invalid repetitions");
    (void)Run(xyz, core, margin);  // CUDA context/JIT warm-up outside steady-state timing.
    std::vector<double> timings_ms;
    timings_ms.reserve(repetitions);
    PipelineResult result;
    for (int index = 0; index < repetitions; ++index) {
      const auto started = std::chrono::steady_clock::now();
      result = Run(xyz, core, margin);
      timings_ms.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count());
    }
    std::sort(timings_ms.begin(), timings_ms.end());
    const double mean = std::accumulate(timings_ms.begin(), timings_ms.end(), 0.0) / timings_ms.size();
    const auto percentile = [&timings_ms](double fraction) {
      return timings_ms[static_cast<std::size_t>(std::ceil(fraction * timings_ms.size())) - 1];
    };
    std::cout << std::fixed << std::setprecision(6)
              << "{\"points\":" << xyz.size() / 3 << ",\"rail_pair_count\":" << result.rails.rail_pairs.size()
              << ",\"rail_axis_reason\":\"" << result.rails.reason << "\",\"core\":" << result.envelope.core_count
              << ",\"margin\":" << result.envelope.margin_count << ",\"outside_reference\":" << result.envelope.outside_reference_count
              << ",\"unknown\":" << result.envelope.unknown_count << ",\"mean_total_ms\":" << mean
              << ",\"p50_total_ms\":" << percentile(.50) << ",\"p95_total_ms\":" << percentile(.95) << "}\n";
  } catch (const std::exception& error) {
    std::cerr << "cuda_pipeline_cli: " << error.what() << '\n';
    return 1;
  }
}
