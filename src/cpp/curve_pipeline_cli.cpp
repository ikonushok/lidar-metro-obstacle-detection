#include "auto_rails_core.hpp"
#include "curve_envelope_core.hpp"

#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

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

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3 && argc != 4) { std::cerr << "usage: curve_pipeline_cli XYZF repetitions [baseline|development_candidate]\n"; return 2; }
  try {
    const auto xyz = ReadXyzf(argv[1]);
    const int repetitions = std::stoi(argv[2]);
    if (repetitions < 1) throw std::runtime_error("repetitions must be positive");
    const std::string requested = argc == 4 ? argv[3] : "development_candidate";
    const auto method = requested == "baseline" ? lidar_mosmetro3d::RailSelectionMethod::kBaseline
                      : requested == "development_candidate" ? lidar_mosmetro3d::RailSelectionMethod::kDevelopmentCandidate
                      : throw std::runtime_error("invalid rail selection method");
    const lidar_mosmetro3d::Bounds core{-1.4, 1.4, 0.0, 3.7};
    const lidar_mosmetro3d::Bounds expanded{-1.9, 1.9, -0.5, 4.2};
    double auto_ms = 0.0, envelope_ms = 0.0;
    lidar_mosmetro3d::AutoRailsResult rails;
    lidar_mosmetro3d::AnalysisResult envelope;
    for (int i = 0; i < repetitions; ++i) {
      auto started = std::chrono::steady_clock::now();
      rails = lidar_mosmetro3d::DetectAutoRails(xyz.data(), xyz.size() / 3, {}, method);
      auto_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
      started = std::chrono::steady_clock::now();
      envelope = lidar_mosmetro3d::AnalyzeCurveEnvelope(xyz.data(), xyz.size() / 3, rails.rail_pairs, core, expanded);
      envelope_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    }
    std::cout << std::fixed << std::setprecision(6)
              << "{\"rail_selection_method\":\"" << lidar_mosmetro3d::RailSelectionMethodName(method)
              << "\",\"status\":\"" << rails.status << "\",\"reason\":\"" << rails.reason << "\",\"rail_pairs\":" << rails.rail_pairs.size()
              << ",\"core\":" << envelope.core_count << ",\"margin\":" << envelope.margin_count
              << ",\"unknown\":" << envelope.unknown_count << ",\"mean_auto_ms\":" << auto_ms / repetitions
              << ",\"mean_envelope_ms\":" << envelope_ms / repetitions
              << ",\"mean_pipeline_ms\":" << (auto_ms + envelope_ms) / repetitions << "}\n";
  } catch (const std::exception& error) {
    std::cerr << "curve_pipeline_cli: " << error.what() << '\n'; return 1;
  }
}
