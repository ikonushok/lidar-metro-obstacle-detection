#include "auto_rails_core.hpp"

#include <cassert>
#include <cmath>
#include <cstddef>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

std::vector<float> ReadXyzf(const char* path) {
  std::ifstream stream(path, std::ios::binary | std::ios::ate);
  if (!stream) throw std::runtime_error("cannot open xyzf");
  const auto bytes = stream.tellg();
  if (bytes <= 0 || bytes % static_cast<std::streamoff>(sizeof(float) * 3) != 0) throw std::runtime_error("invalid xyzf");
  std::vector<float> xyz(static_cast<std::size_t>(bytes) / sizeof(float));
  stream.seekg(0);
  stream.read(reinterpret_cast<char*>(xyz.data()), bytes);
  if (!stream) throw std::runtime_error("cannot read xyzf");
  return xyz;
}

void SamePairs(const std::vector<lidar_mosmetro3d::RailPair>& left,
               const std::vector<lidar_mosmetro3d::RailPair>& right) {
  assert(left.size() == right.size());
  for (std::size_t index = 0; index < left.size(); ++index) {
    assert(left[index].source_s_m == right[index].source_s_m);
    assert(left[index].left.x == right[index].left.x && left[index].left.y == right[index].left.y && left[index].left.z == right[index].left.z);
    assert(left[index].right.x == right[index].right.x && left[index].right.y == right[index].right.y && left[index].right.z == right[index].right.z);
  }
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const auto xyz = ReadXyzf(argv[1]);
  const auto implicit_candidate = lidar_mosmetro3d::DetectAutoRails(xyz.data(), xyz.size() / 3);
  const auto explicit_candidate = lidar_mosmetro3d::DetectAutoRails(
      xyz.data(), xyz.size() / 3, {}, lidar_mosmetro3d::RailSelectionMethod::kDevelopmentCandidate);
  assert(implicit_candidate.status == explicit_candidate.status);
  assert(implicit_candidate.reason == explicit_candidate.reason);
  SamePairs(implicit_candidate.rail_pairs, explicit_candidate.rail_pairs);
  assert(explicit_candidate.status == "AUTO_HYPOTHESIS");
  assert(explicit_candidate.reason == "PAIRED_RAISED_LOCAL_CONTINUITY_PATH");
  assert(explicit_candidate.rail_pairs.size() == 16);
  for (std::size_t index = 1; index < explicit_candidate.rail_pairs.size(); ++index) {
    // No synthetic end pair: every returned pair came from an observed station bin.
    assert(explicit_candidate.rail_pairs[index].source_s_m > explicit_candidate.rail_pairs[index - 1].source_s_m);
    assert(explicit_candidate.rail_pairs[index].source_s_m - explicit_candidate.rail_pairs[index - 1].source_s_m <= 6.0);
  }

  const auto explicit_baseline = lidar_mosmetro3d::DetectAutoRails(
      xyz.data(), xyz.size() / 3, {}, lidar_mosmetro3d::RailSelectionMethod::kBaseline);
  assert(explicit_baseline.status == "UNKNOWN");
  assert(explicit_baseline.reason == "NO_STRAIGHT_CONSISTENT_PAIR");

  const std::vector<float> insufficient{0.0F, -4.0F, 0.0F};
  const auto unknown = lidar_mosmetro3d::DetectAutoRails(
      insufficient.data(), 1, {}, lidar_mosmetro3d::RailSelectionMethod::kDevelopmentCandidate);
  assert(unknown.status == "UNKNOWN");
  assert(unknown.rail_pairs.empty());
  const auto invalid = lidar_mosmetro3d::DetectAutoRails(
      insufficient.data(), 1, {}, static_cast<lidar_mosmetro3d::RailSelectionMethod>(99));
  assert(invalid.status == "UNKNOWN");
  assert(invalid.reason == "INVALID_RAIL_SELECTION_METHOD");
  std::cout << "auto_rails_selection_test: PASS\n";
}
