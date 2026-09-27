'use strict';

// Read-only summary of the fixed Stage 5 paired experiment.
// Usage: node scripts/stage_5_compare_summary.cjs <comparison.json> <summary.json>
const fs = require('node:fs');
const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node scripts/stage_5_compare_summary.cjs <comparison.json> <summary.json>');

const comparison = JSON.parse(fs.readFileSync(input, 'utf8'));
const records = comparison.records.filter((record) => !record.synthetic);
const sum = (values) => values.reduce((total, value) => total + value, 0);
const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const half = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(half)] : (sorted[half - 1] + sorted[half]) / 2;
};
const tolerance = 1e-9;
const perFrame = records.map((record) => ({
  id: record.id,
  baseline_status: record.baseline.status,
  supported_length_delta_m: record.candidate.supported_length_m - record.baseline.supported_length_m,
  unknown_return_delta: record.candidate.intersection.counts.unknown - record.baseline.intersection.counts.unknown,
  core_return_delta: (record.candidate.intersection.counts.core || 0) - (record.baseline.intersection.counts.core || 0),
  median_compute_delta_ms: record.candidate.compute_ms.median - record.baseline.compute_ms.median,
}));
const positive = perFrame.filter((record) => record.supported_length_delta_m > tolerance).length;
const negative = perFrame.filter((record) => record.supported_length_delta_m < -tolerance).length;
const ties = perFrame.length - positive - negative;
const totalPoints = sum(records.map((record) => record.point_count));
const baselineLength = sum(records.map((record) => record.baseline.supported_length_m));
const candidateLength = sum(records.map((record) => record.candidate.supported_length_m));
const baselineUnknown = sum(records.map((record) => record.baseline.intersection.counts.unknown));
const candidateUnknown = sum(records.map((record) => record.candidate.intersection.counts.unknown));
const supportedByBaseline = perFrame.filter((record) => record.baseline_status !== 'UNKNOWN');
const timeDelta = perFrame.map((record) => record.median_compute_delta_ms);
const timeDeltaSupported = supportedByBaseline.map((record) => record.median_compute_delta_ms);

const summary = {
  format: 'stage_5_pairwise_summary_v1',
  scope: 'EIGHT_REAL_SINGLE_FRAME_DEVELOPMENT_CASES; NOT_AXIS_GROUND_TRUTH_OR_OBJECT_DETECTION_PRECISION_RECALL',
  source_comparison: input,
  unit_of_analysis: 'frame; returns are correlated within a frame and are not independent samples',
  real_frames: records.length,
  total_raw_returns: totalPoints,
  supported_length_m: {
    baseline_total: baselineLength,
    candidate_total: candidateLength,
    candidate_minus_baseline: candidateLength - baselineLength,
    relative_change_percent: 100 * (candidateLength - baselineLength) / baselineLength,
    frame_wins: { candidate_better: positive, candidate_worse: negative, equal: ties },
    exploratory_exact_one_sided_sign_test_p_excluding_ties: Math.pow(0.5, positive),
    interpretation: 'Four non-tied improvements and zero degradations; p=0.0625 is above alpha=0.05, so this small development set does not establish formal statistical significance.',
  },
  unknown_returns: {
    baseline: baselineUnknown,
    candidate: candidateUnknown,
    candidate_minus_baseline: candidateUnknown - baselineUnknown,
    relative_change_percent: 100 * (candidateUnknown - baselineUnknown) / baselineUnknown,
    baseline_fraction_of_all_returns: baselineUnknown / totalPoints,
    candidate_fraction_of_all_returns: candidateUnknown / totalPoints,
    change_percentage_points_of_all_returns: 100 * (candidateUnknown - baselineUnknown) / totalPoints,
    interpretation: 'UNKNOWN is not CLEAR. This is coverage only, not a proven safety or accuracy gain.',
  },
  observed_core_returns: {
    per_frame_candidate_minus_baseline: perFrame.map(({ id, core_return_delta }) => ({ id, core_return_delta })),
    interpretation: 'No class/static/map suppression was used. Counts are not TP/FP without labels.',
  },
  compute_time_median_ms: {
    all_frames_mean_candidate_minus_baseline: sum(timeDelta) / timeDelta.length,
    all_frames_median_candidate_minus_baseline: median(timeDelta),
    baseline_supported_frames: supportedByBaseline.length,
    baseline_supported_mean_candidate_minus_baseline: sum(timeDeltaSupported) / timeDeltaSupported.length,
    baseline_supported_median_candidate_minus_baseline: median(timeDeltaSupported),
  },
  per_frame: perFrame,
  decision: 'BETTER_ON_MEASURED_COVERAGE_WITH_NO_OBSERVED_REGRESSION; NOT_FORMALLY_SIGNIFICANT_AT_ALPHA_0_05_AND_NOT_A_PROVEN_AXIS_ACCURACY_IMPROVEMENT',
};

fs.writeFileSync(output, `${JSON.stringify(summary, null, 2)}\n`);
console.log(JSON.stringify(summary, null, 2));
