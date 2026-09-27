#include "cuda_envelope.hpp"

#include <cuda_runtime.h>

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace lidar_mosmetro3d {
namespace {

constexpr double kTolerance = 1e-6;

struct DeviceSegment {
  double ax, ay, az;
  double tx, ty, nx, ny;
  double dz, length;
};

void Check(cudaError_t error, const char* operation) {
  if (error != cudaSuccess) throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(error));
}

std::vector<DeviceSegment> BuildSegmentsForCuda(const std::vector<RailPair>& input) {
  const auto pairs = ValidateRailPairs(input);
  std::vector<DeviceSegment> result;
  result.reserve(pairs.size() - 1);
  for (std::size_t index = 0; index + 1 < pairs.size(); ++index) {
    // Keep the CPU reference's float midpoint rounding before double geometry.
    const Point3f a{static_cast<float>((pairs[index].left.x + pairs[index].right.x) * .5),
                   static_cast<float>((pairs[index].left.y + pairs[index].right.y) * .5),
                   static_cast<float>((pairs[index].left.z + pairs[index].right.z) * .5)};
    const Point3f b{static_cast<float>((pairs[index + 1].left.x + pairs[index + 1].right.x) * .5),
                   static_cast<float>((pairs[index + 1].left.y + pairs[index + 1].right.y) * .5),
                   static_cast<float>((pairs[index + 1].left.z + pairs[index + 1].right.z) * .5)};
    const double dx = static_cast<double>(b.x) - a.x;
    const double dy = static_cast<double>(b.y) - a.y;
    const double length = std::hypot(dx, dy);
    if (length < kTolerance) throw std::invalid_argument("adjacent curve sections must differ");
    double nx = dy / length, ny = -dx / length;
    const double side_x = pairs[index].left.x - pairs[index].right.x;
    const double side_y = pairs[index].left.y - pairs[index].right.y;
    if (nx * side_x + ny * side_y < 0.0) { nx = -nx; ny = -ny; }
    result.push_back({a.x, a.y, a.z, dx / length, dy / length, nx, ny,
                      static_cast<double>(b.z) - a.z, length});
  }
  return result;
}

__global__ void ClassifyKernel(const float* xyz, std::size_t point_count,
                               const DeviceSegment* segments, std::size_t segment_count,
                               Bounds core, Bounds expanded, std::uint8_t* labels) {
  const std::size_t index = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= point_count) return;
  const double px = xyz[index * 3], py = xyz[index * 3 + 1], pz = xyz[index * 3 + 2];
  std::uint8_t zone = static_cast<std::uint8_t>(Zone::kUnknown);
  for (std::size_t segment_index = 0; segment_index < segment_count; ++segment_index) {
    const auto& segment = segments[segment_index];
    const double dx = px - segment.ax, dy = py - segment.ay;
    const double station = dx * segment.tx + dy * segment.ty;
    if (station < -kTolerance || station > segment.length + kTolerance) continue;
    const double lateral = dx * segment.nx + dy * segment.ny;
    const double height = pz - segment.az - segment.dz * station / segment.length;
    const bool in_core = lateral >= core.left - kTolerance && lateral <= core.right + kTolerance &&
                         height >= core.bottom - kTolerance && height <= core.top + kTolerance;
    if (in_core) { zone = static_cast<std::uint8_t>(Zone::kCore); break; }
    const bool in_margin = lateral >= expanded.left - kTolerance && lateral <= expanded.right + kTolerance &&
                           height >= expanded.bottom - kTolerance && height <= expanded.top + kTolerance;
    if (zone == static_cast<std::uint8_t>(Zone::kUnknown))
      zone = static_cast<std::uint8_t>(in_margin ? Zone::kMargin : Zone::kOutsideReference);
  }
  labels[index] = zone;
}

AnalysisResult Summarize(const float* xyz, std::size_t point_count, std::vector<std::uint8_t> labels) {
  AnalysisResult result;
  result.labels.reserve(point_count);
  for (std::size_t index = 0; index < point_count; ++index) {
    const auto zone = static_cast<Zone>(labels[index]);
    result.labels.push_back(zone);
    switch (zone) {
      case Zone::kCore: ++result.core_count; break;
      case Zone::kMargin: ++result.margin_count; break;
      case Zone::kOutsideReference: ++result.outside_reference_count; break;
      case Zone::kUnknown: ++result.unknown_count; break;
    }
    if (zone != Zone::kCore && zone != Zone::kMargin) continue;
    const double distance = std::hypot(static_cast<double>(xyz[index * 3]), xyz[index * 3 + 1], xyz[index * 3 + 2]);
    auto* nearest = zone == Zone::kCore ? &result.nearest_core : &result.nearest_margin;
    if (distance < nearest->distance_from_source_origin_m) {
      nearest->source_index = index;
      nearest->distance_from_source_origin_m = distance;
    }
  }
  return result;
}

}  // namespace

bool CudaEnvelopeAvailable(std::string* reason) {
  int count = 0;
  const auto status = cudaGetDeviceCount(&count);
  if (status == cudaSuccess && count > 0) return true;
  if (reason) *reason = status == cudaSuccess ? "CUDA_DEVICE_NOT_FOUND" : cudaGetErrorString(status);
  return false;
}

AnalysisResult AnalyzeCurveEnvelopeCuda(const float* xyz, std::size_t point_count,
                                        const std::vector<RailPair>& pairs,
                                        const Bounds& core, const Bounds& expanded,
                                        const CoreNoiseFilterConfig& noise_config) {
  if (!xyz) throw std::invalid_argument("xyz must not be null");
  if (pairs.empty()) return AnalyzeCurveEnvelope(xyz, point_count, pairs, core, expanded, noise_config);
  if (!(core.left < core.right && core.bottom < core.top && expanded.left <= core.left && expanded.right >= core.right &&
        expanded.bottom <= core.bottom && expanded.top >= core.top)) throw std::invalid_argument("invalid envelope bounds");
  const auto segments = BuildSegmentsForCuda(pairs);
  for (std::size_t index = 0; index < point_count * 3; ++index)
    if (!std::isfinite(xyz[index])) throw std::invalid_argument("xyz must be finite");
  float* device_xyz = nullptr; DeviceSegment* device_segments = nullptr; std::uint8_t* device_labels = nullptr;
  try {
    Check(cudaMalloc(&device_xyz, point_count * 3 * sizeof(float)), "cudaMalloc xyz");
    Check(cudaMalloc(&device_segments, segments.size() * sizeof(DeviceSegment)), "cudaMalloc segments");
    Check(cudaMalloc(&device_labels, point_count * sizeof(std::uint8_t)), "cudaMalloc labels");
    Check(cudaMemcpy(device_xyz, xyz, point_count * 3 * sizeof(float), cudaMemcpyHostToDevice), "cudaMemcpy xyz");
    Check(cudaMemcpy(device_segments, segments.data(), segments.size() * sizeof(DeviceSegment), cudaMemcpyHostToDevice), "cudaMemcpy segments");
    constexpr int threads = 256;
    ClassifyKernel<<<static_cast<unsigned>((point_count + threads - 1) / threads), threads>>>(device_xyz, point_count, device_segments, segments.size(), core, expanded, device_labels);
    Check(cudaGetLastError(), "ClassifyKernel launch"); Check(cudaDeviceSynchronize(), "ClassifyKernel synchronize");
    std::vector<std::uint8_t> labels(point_count);
    Check(cudaMemcpy(labels.data(), device_labels, point_count * sizeof(std::uint8_t), cudaMemcpyDeviceToHost), "cudaMemcpy labels");
    cudaFree(device_xyz); cudaFree(device_segments); cudaFree(device_labels);
    auto result = Summarize(xyz, point_count, std::move(labels));
    ApplyCoreNoiseFilter(xyz, point_count, result, pairs, noise_config);
    return result;
  } catch (...) {
    if (device_xyz) cudaFree(device_xyz); if (device_segments) cudaFree(device_segments); if (device_labels) cudaFree(device_labels);
    throw;
  }
}

}  // namespace lidar_mosmetro3d
