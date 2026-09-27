#include "auto_rails_core.hpp"

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
  if (argc != 3) { std::cerr << "usage: auto_rails_cli XYZF OUTPUT_PAIRS_CSV\n"; return 2; }
  try {
    const auto xyz = ReadXyzf(argv[1]);
    const auto result = lidar_mosmetro3d::DetectAutoRails(xyz.data(), xyz.size() / 3);
    std::ofstream output(argv[2]);
    if (!output) throw std::runtime_error("cannot open pairs output");
    output << std::setprecision(17);
    for (const auto& pair : result.rail_pairs) {
      output << pair.source_s_m << ',' << pair.left.x << ',' << pair.left.y << ',' << pair.left.z << ','
             << pair.right.x << ',' << pair.right.y << ',' << pair.right.z << '\n';
    }
    std::cout << "{\"status\":\"" << result.status << "\",\"reason\":\"" << result.reason
              << "\",\"rail_pairs\":" << result.rail_pairs.size() << ",\"supported_stations\":"
              << result.supported_stations << ",\"rms\":" << std::setprecision(17) << result.rms << "}\n";
  } catch (const std::exception& error) {
    std::cerr << "auto_rails_cli: " << error.what() << '\n'; return 1;
  }
}
