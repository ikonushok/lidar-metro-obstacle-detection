#include "curve_envelope_core.hpp"

#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
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
  if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(float) * 3) != 0)
    throw std::runtime_error("xyzf must contain float32 XYZ triplets");
  std::vector<float> xyz(static_cast<std::size_t>(bytes) / sizeof(float));
  stream.seekg(0);
  stream.read(reinterpret_cast<char*>(xyz.data()), bytes);
  if (!stream) throw std::runtime_error("cannot read xyzf");
  return xyz;
}

std::vector<RailPair> ReadPairs(const std::string& path) {
  std::ifstream stream(path);
  if (!stream) throw std::runtime_error("cannot open rail pairs");
  std::vector<RailPair> pairs;
  std::string line;
  while (std::getline(stream, line)) {
    if (line.empty()) continue;
    std::istringstream values(line);
    RailPair pair{};
    char comma = 0;
    if (!(values >> pair.source_s_m >> comma) || comma != ',' ||
        !(values >> pair.left.x >> comma) || comma != ',' ||
        !(values >> pair.left.y >> comma) || comma != ',' ||
        !(values >> pair.left.z >> comma) || comma != ',' ||
        !(values >> pair.right.x >> comma) || comma != ',' ||
        !(values >> pair.right.y >> comma) || comma != ',' ||
        !(values >> pair.right.z))
      throw std::runtime_error("invalid rail pair CSV");
    pairs.push_back(pair);
  }
  return pairs;
}

double Number(const char* text) {
  std::size_t used = 0;
  const auto value = std::stod(text, &used);
  if (text[used] != '\0') throw std::runtime_error("invalid numeric argument");
  return value;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 12 && argc != 13) {
    std::cerr << "usage: curve_envelope_cli XYZF PAIRS_CSV core_left core_right core_bottom core_top "
                 "margin_left margin_right margin_bottom margin_top repetitions\n";
    return 2;
  }
  try {
    const auto xyz = ReadXyzf(argv[1]);
    const auto pairs = ReadPairs(argv[2]);
    const Bounds core{Number(argv[3]), Number(argv[4]), Number(argv[5]), Number(argv[6])};
    const Bounds margin{Number(argv[7]), Number(argv[8]), Number(argv[9]), Number(argv[10])};
    const int repetitions = std::stoi(argv[11]);
    if (repetitions < 1) throw std::runtime_error("repetitions must be positive");
    lidar_mosmetro3d::AnalysisResult result;
    double elapsed_ms = 0.0;
    for (int i = 0; i < repetitions; ++i) {
      const auto started = std::chrono::steady_clock::now();
      result = lidar_mosmetro3d::AnalyzeCurveEnvelope(xyz.data(), xyz.size() / 3, pairs, core, margin);
      elapsed_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    }
    if (argc == 13) {
      std::ofstream labels(argv[12], std::ios::binary);
      if (!labels) throw std::runtime_error("cannot open labels output");
      for (const auto zone : result.labels) {
        const auto byte = static_cast<std::uint8_t>(zone);
        labels.write(reinterpret_cast<const char*>(&byte), sizeof(byte));
      }
      if (!labels) throw std::runtime_error("cannot write labels output");
    }
    const auto nearest = [](const lidar_mosmetro3d::NearestPoint& value) {
      return value.source_index == std::numeric_limits<std::size_t>::max()
                 ? "null"
                 : std::to_string(value.source_index);
    };
    std::cout << std::fixed << std::setprecision(6)
              << "{\"points\":" << xyz.size() / 3
              << ",\"rail_pairs\":" << pairs.size()
              << ",\"core\":" << result.core_count
              << ",\"margin\":" << result.margin_count
              << ",\"outside_reference\":" << result.outside_reference_count
              << ",\"unknown\":" << result.unknown_count
              << ",\"nearest_core_index\":" << nearest(result.nearest_core)
              << ",\"nearest_margin_index\":" << nearest(result.nearest_margin)
              << ",\"mean_compute_ms\":" << elapsed_ms / repetitions << "}\n";
  } catch (const std::exception& error) {
    std::cerr << "curve_envelope_cli: " << error.what() << '\n';
    return 1;
  }
}
