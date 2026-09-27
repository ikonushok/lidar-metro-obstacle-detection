#include "cuda_envelope.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using lidar_mosmetro3d::Bounds;
using lidar_mosmetro3d::Point3f;
using lidar_mosmetro3d::RailPair;

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

std::vector<RailPair> ReadPairs(const std::string& path) {
  std::ifstream stream(path); if (!stream) throw std::runtime_error("cannot open rail pairs");
  std::vector<RailPair> pairs; std::string line;
  while (std::getline(stream, line)) {
    if (line.empty()) continue; std::istringstream values(line); RailPair pair{}; char comma = 0;
    if (!(values >> pair.source_s_m >> comma) || comma != ',' || !(values >> pair.left.x >> comma) || comma != ',' ||
        !(values >> pair.left.y >> comma) || comma != ',' || !(values >> pair.left.z >> comma) || comma != ',' ||
        !(values >> pair.right.x >> comma) || comma != ',' || !(values >> pair.right.y >> comma) || comma != ',' ||
        !(values >> pair.right.z)) throw std::runtime_error("invalid rail pair CSV");
    pairs.push_back(pair);
  }
  return pairs;
}

void WriteLabels(const std::string& path, const lidar_mosmetro3d::AnalysisResult& result) {
  std::ofstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot create labels file");
  for (const auto label : result.labels) {
    const auto byte = static_cast<std::uint8_t>(label);
    stream.write(reinterpret_cast<const char*>(&byte), sizeof(byte));
  }
  if (!stream) throw std::runtime_error("cannot write labels file");
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 12 && argc != 13) { std::cerr << "usage: cuda_envelope_cli XYZF PAIRS core_left core_right core_bottom core_top margin_left margin_right margin_bottom margin_top repetitions [LABELS_BIN]\n"; return 2; }
  try {
    const auto xyz = ReadXyzf(argv[1]); const auto pairs = ReadPairs(argv[2]);
    const Bounds core{std::stod(argv[3]), std::stod(argv[4]), std::stod(argv[5]), std::stod(argv[6])};
    const Bounds margin{std::stod(argv[7]), std::stod(argv[8]), std::stod(argv[9]), std::stod(argv[10])};
    const int repetitions = std::stoi(argv[11]); if (repetitions < 1) throw std::runtime_error("invalid repetitions");
    lidar_mosmetro3d::AnalysisResult result;
    // Initialize the CUDA context and JIT outside of steady-state per-frame timing.
    result = lidar_mosmetro3d::AnalyzeCurveEnvelopeCuda(xyz.data(), xyz.size() / 3, pairs, core, margin);
    std::vector<double> timings_ms; timings_ms.reserve(repetitions);
    for (int i = 0; i < repetitions; ++i) {
      const auto started = std::chrono::steady_clock::now();
      result = lidar_mosmetro3d::AnalyzeCurveEnvelopeCuda(xyz.data(), xyz.size() / 3, pairs, core, margin);
      timings_ms.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count());
    }
    if (argc == 13) WriteLabels(argv[12], result);
    std::sort(timings_ms.begin(), timings_ms.end());
    const double mean = std::accumulate(timings_ms.begin(), timings_ms.end(), 0.0) / timings_ms.size();
    const auto percentile = [&timings_ms](double fraction) {
      return timings_ms[static_cast<std::size_t>(std::ceil(fraction * timings_ms.size())) - 1];
    };
    std::cout << std::fixed << std::setprecision(6) << "{\"points\":" << xyz.size() / 3 << ",\"core\":" << result.core_count
              << ",\"margin\":" << result.margin_count << ",\"outside_reference\":" << result.outside_reference_count
              << ",\"unknown\":" << result.unknown_count << ",\"nearest_core_index\":"
              << (result.nearest_core.source_index == std::numeric_limits<std::size_t>::max() ? "null" : std::to_string(result.nearest_core.source_index))
              << ",\"nearest_margin_index\":"
              << (result.nearest_margin.source_index == std::numeric_limits<std::size_t>::max() ? "null" : std::to_string(result.nearest_margin.source_index))
              << ",\"mean_total_ms\":" << mean << ",\"p50_total_ms\":" << percentile(.50)
              << ",\"p95_total_ms\":" << percentile(.95) << "}\n";
  } catch (const std::exception& error) { std::cerr << "cuda_envelope_cli: " << error.what() << '\n'; return 1; }
}
