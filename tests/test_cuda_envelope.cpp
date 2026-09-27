#include "cuda_envelope.hpp"

#include <cassert>
#include <vector>

int main() {
  using namespace lidar_mosmetro3d;
  std::string reason;
  assert(CudaEnvelopeAvailable(&reason));
  const std::vector<RailPair> pairs{
      {4.0, {-1.0F, -4.0F, 0.0F}, {1.0F, -4.0F, 0.0F}},
      {6.0, {-1.1F, -6.0F, 0.0F}, {0.9F, -6.0F, 0.0F}},
      {8.0, {-1.5F, -8.0F, 0.0F}, {0.5F, -8.0F, 0.0F}},
  };
  const Bounds core{-1.4, 1.4, 0.0, 3.7}, expanded{-1.9, 1.9, -0.5, 4.2};
  const std::vector<float> raw{0.0F, -4.5F, .005F, 1.7F, -4.5F, 1.0F, 2.2F, -4.5F, 1.0F,
                               0.0F, -3.9F, 1.0F, -.8F, -9.0F, 1.0F};
  const auto cpu = AnalyzeCurveEnvelope(raw.data(), raw.size() / 3, pairs, core, expanded);
  const auto gpu = AnalyzeCurveEnvelopeCuda(raw.data(), raw.size() / 3, pairs, core, expanded);
  assert(cpu.labels == gpu.labels);
  assert(cpu.core_count == gpu.core_count && cpu.margin_count == gpu.margin_count &&
         cpu.outside_reference_count == gpu.outside_reference_count && cpu.unknown_count == gpu.unknown_count);
  assert(cpu.nearest_core.source_index == gpu.nearest_core.source_index);
  assert(cpu.nearest_margin.source_index == gpu.nearest_margin.source_index);
}
