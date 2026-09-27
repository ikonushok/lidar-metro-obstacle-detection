#include "cuda_envelope.hpp"

#include <stdexcept>

namespace lidar_mosmetro3d {

bool CudaEnvelopeAvailable(std::string* reason) {
  if (reason) *reason = "CUDA_NOT_COMPILED";
  return false;
}

AnalysisResult AnalyzeCurveEnvelopeCuda(const float*, std::size_t,
                                        const std::vector<RailPair>&,
                                        const Bounds&, const Bounds&,
                                        const CoreNoiseFilterConfig&) {
  throw std::runtime_error("CUDA_NOT_COMPILED");
}

}  // namespace lidar_mosmetro3d
