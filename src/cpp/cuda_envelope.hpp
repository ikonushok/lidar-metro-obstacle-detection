#pragma once

#include "curve_envelope_core.hpp"

#include <string>

namespace lidar_mosmetro3d {

// CUDA is an optional accelerator. The function throws when the compiled
// backend or an NVIDIA device is unavailable; callers decide CPU fallback.
bool CudaEnvelopeAvailable(std::string* reason);
AnalysisResult AnalyzeCurveEnvelopeCuda(const float* xyz, std::size_t point_count,
                                        const std::vector<RailPair>& pairs,
                                        const Bounds& core, const Bounds& expanded,
                                        const CoreNoiseFilterConfig& noise_config = {});

}  // namespace lidar_mosmetro3d
