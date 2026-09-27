# Stage 5: geometry-first cloud candidate decision note

Дата: 2026-09-25.

## Decision

Текущий лучший cloud-focused offline candidate:

```text
geometry-first gate + boundary warning + conservative ML suppressor
```

Detector field for obstacle scoring:

```text
geometry_gate_ml_suppressor_obstacle
```

Boundary/warning field:

```text
geometry_boundary_warning
```

Это offline candidate screening, не ROS2/C++ runtime integration.

## Working benchmark scope

`cloud_with_fake_obj` после раскрытия состава организаторами используется как development benchmark, не independent held-out.

Current scorable cloud labels:

| Group | Events |
|---|---|
| Target positives | #1, #2, #3, #4, #6, #9 |
| Boundary negatives | #7 outside, #8 above |
| Unlocalized/unscorable | #5 outside close, #10 narrow hanging |

#10 remains positive only as a formulation target if future evidence confirms CORE-gabarit intersection. Current full-cloud scan did not confirm that.

## Current result

On updated `docs/stages/stage_5/cloud_with_fake_obj_working_labels.json`:

| Detector | Positive hits | Positive unlocalized | Boundary obstacle FP | Boundary scorable | Obstacle alarms | Unassigned obstacle alarms |
|---|---:|---:|---:|---:|---:|---:|
| `geometry_gate_ml_suppressor_obstacle` | 6/6 | 1 (#10) | 0 | 2 (#7/#8) | 26 | 1 |

Boundary warning evidence:

- #7 outside: warning run around `625..633`; obstacle alarm is suppressed in `630..633`.
- #8 above: visual-confirmed boundary interval `674..681`; warning run `675..681`; obstacle alarm is suppressed.
- Warning is not `CLEAR` and not target `obstacle`.

## Why this candidate

Raw CORE `>=1000` is a useful high-support proposal, but it falsely treats #7 outside as obstacle.

The accepted offline candidate keeps high-support inside/core positives, while separating known outside/above geometry:

```text
obstacle = strong CORE geometry, except explicit boundary-warning shapes
warning  = outside-left thin/tall or upper/above broad geometry
ML       = conservative suppressor for weak components; cannot delete strong geometry positives
```

The learned suppressor currently selects threshold `1.0` and lets through no uncertain components, so the measured improvement comes from geometry-first boundary handling, not from ML recall.

## DoubleT position

This cloud gate is not a universal detector and does not replace the existing doubleT/model path.

On `doubleT_obstacle` with the cloud-trained gate:

```text
geometry_gate_ml_suppressor_obstacle: 0/1 event, 0 alarm frames
```

Interpretation:

- `doubleT_obstacle` remains sanity/regression for the older known positive.
- Preserving doubleT requires the existing temporal/model path or a separate small-support branch.
- Do not present this cloud geometry gate as a replacement for `model_v1`/current temporal path.

## Evidence

Primary artifacts:

- `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/gate_ml_working_labels_cloud_eval.json`
- `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/visual_confirm_summary.json`
- `artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/hanging_candidate_scan.json`
- `artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/hanging_candidate_scan_wide.json`
- `artefacts/stage_5/geometry_gate_ml_suppressor_20260925/`

Main report:

- `docs/stages/stage_5/stage_5_geometry_first_candidate_screening.md`

Scripts:

- `scripts/screen_geometry_gate_ml_suppressor.py`
- `scripts/screen_geometry_first_candidate.py`
- `scripts/summarize_geometry_first_candidate.py`
- `scripts/localize_cloud_synthetic_objects.py`
- `scripts/render_cloud_boundary_visual_confirm.py`
- `scripts/scan_cloud_hanging_candidates.py`

## Validation level

Achieved: L1 for saved offline JSON/evaluator outputs and visual-only frame evidence.

Not achieved:

- no runtime validation;
- no ROS2/C++ integration;
- no independent held-out claim;
- no final GT box-level validation;
- no confirmation that #10 intersects CORE.

## Next action

Use this candidate as the current cloud development baseline:

```text
cloud dev baseline = geometry_gate_ml_suppressor_obstacle
with geometry_boundary_warning reported separately
```

Next minimal engineering step is not integration. It is a design decision:

- either keep it as an offline benchmark candidate only;
- or open a separate runtime-design task that explicitly specifies how boundary warning, obstacle alarm, UNKNOWN, and the existing temporal/model path compose.
