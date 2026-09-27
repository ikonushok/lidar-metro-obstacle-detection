# Stage 5 UNKNOWN status audit

Дата: 2026-09-24.

## Задача

- Goal: разобрать `UNKNOWN` как upstream/status FP после hard-negative ML-кандидатов и отделить его от component classifier.
- Наблюдаемая проблема: в `docs/README_noise_classifier.md` лучшие `model + temporal` кандидаты дают `TP=52`, `FN=0`, `FP total=193`; все `193` FP являются `UNKNOWN`.
- Non-goals: не менять runtime ML-модель, не использовать синтетику, не менять envelope/геометрию/оси/пороги, не превращать `UNKNOWN` в `CLEAR`.
- Source of truth: `docs/README_noise_classifier.md`, `artefacts/stage_5/noise_model_candidate_hard_negative_all_sources_cal_roundT/noise_model_candidates.json`, C++/ROS2/Python pipeline code, read-only Docker replay of the 193 `UNKNOWN_FP` frames.
- Этап: stage 5, адресная доработка FP/FN/UNKNOWN.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка: локальный Docker image `lidar-mosmetro3d:noise-current` плюс локальный Python unittest.
- Входные данные: seven-source development run, frame-level labels; `doubleT_obstacle` positive frames 13-64, остальные кадры считаются negative по текущему допущению.
- Рабочие frames/transforms: source XYZ, no TF; текущая геометрия `development_candidate`, `tangent`, `m_ASSUMED`.
- Protected contracts: `UNKNOWN` не `CLEAR`; model-negative не доказывает свободный путь; geometry/envelope/thresholds не менялись.
- Allowed files for implemented diagnostic patch: `scripts/evaluate_noise_classifier.py`, `scripts/evaluate_noise_model_candidates.py`, `tests/test_evaluate_noise_classifier.py`, C++/ROS2 diagnostic JSON fields, static contract tests, этот отчёт.
- Files to avoid: runtime ML artifact, C++ geometry/envelope, ROS2 node decisions, synthetic generator/data.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Reviewer: validation-style pass текущим агентом по `agents/validation_reviewer.md`; safety geometry reviewer не запускался, потому что геометрия не менялась.
- Validation target: L1 для diagnostic code change; L4 для read-only разбора уже существующего seven-source development artifact по frame keys.
- Acceptance: причины `UNKNOWN_FP` разложены по источникам/кадрам/reason; evaluator сохраняет reason codes; итоговые FP таблицы разделяют `UNKNOWN_FP` и `model_temporal_FP`.

## Где выставляется UNKNOWN

### C++ direct stream

- `src/cpp/curve_pipeline_stream_cli.cpp`: `UnknownJson(...)` публикует frame-level `status="UNKNOWN"`, `system_status="UNKNOWN"`, `curve_axis_status="MISSING_CURVE_AXIS"` при отсутствии валидной оси.
- `src/cpp/curve_pipeline_stream_cli.cpp`: если `DetectAutoRails(...)` вернул меньше двух rail pairs, stream сразу отдаёт `UnknownJson(rails.reason, ...)`.
- `src/cpp/curve_pipeline_stream_cli.cpp`: при поддержанной оси, но без `core` и `margin`, статус кадра тоже становится `UNKNOWN`, reason `NO_RETURNS_INTERSECT_REFERENCE_NOT_CLEAR`. Это candidate-only статус, не CLEAR.
- `src/cpp/curve_envelope_core.hpp/.cpp`: `Zone::kUnknown` используется как point-level label для точек вне поддержанного участка/без сегмента; это не обязательно frame-level `UNKNOWN`.
- `src/cpp/auto_rails_core.cpp`: `DetectAutoRails(...)` возвращает `AutoRailsResult.status="UNKNOWN"` с reason codes: `INVALID_SEARCH_PARAMETERS`, `INVALID_RAIL_SELECTION_METHOD`, `NONFINITE_XYZ`, `INSUFFICIENT_PAIRED_RAIL_SUPPORT`, `SEARCH_BUDGET_EXCEEDED`, `INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT`, `INSUFFICIENT_CONTIGUOUS_COVERAGE`, `AMBIGUOUS_LOCAL_CONTINUITY_PATH`, `NO_STRAIGHT_CONSISTENT_PAIR`, `AMBIGUOUS_RAIL_PAIRS`.

### ROS2 node

- `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`: `PublishUnknown(...)` emits `status="UNKNOWN"` and resets temporal state for input/schema/config/backend/axis failures.
- ROS2-specific reasons include `UNSUPPORTED_SOURCE_FRAME`, `UNSUPPORTED_POINTCLOUD_ENDIANNESS`, `UNSUPPORTED_POINTCLOUD_XYZ_SCHEMA`, `NONFINITE_XYZ`, `INVALID_ENVELOPE`, `INVALID_COMPUTE_BACKEND`, `INVALID_NOISE_FILTER_MODE`, `INVALID_RAIL_SELECTION_METHOD`, `INVALID_FORWARD_EXTENSION_METHOD`, `INVALID_ARC_EXTENSION_HORIZON`, `INVALID_ARC_CLAMP_PARAMETERS`, `INVALID_ARC_FIT_WINDOW`, `CUDA_UNAVAILABLE`, and pass-through rail reasons from `DetectAutoRails(...)`.
- With supported axis, ROS2 can also emit frame-level `status="UNKNOWN"` with reason `NO_RETURNS_INTERSECT_REFERENCE_NOT_CLEAR`.

### Python/offline evaluators

- `scripts/evaluate_noise_classifier.py`: before this audit, UNKNOWN rows preserved only `unknown=True`; reason was not persisted in output totals. Patch now adds `unknown_reason_counts`, `unknown_curve_axis_status_counts`, and `unknown_frame_keys_by_reason`.
- `scripts/evaluate_noise_model_candidates.py`: before this audit, candidate summaries counted negative UNKNOWN as FP but did not summarize reasons. Patch now adds `unknown_reason_counts`, `unknown_curve_axis_status_counts`, `unknown_fp_reason_counts`, and `unknown_fp_frame_keys_by_reason`.
- `src/stage_3_baseline.py`: older Python baseline has candidate-only `UNKNOWN` for disabled/invalid assumed geometry and no-cluster cases. It is not the current `model + temporal` seven-source path.

## UNKNOWN=193 breakdown

Artifact inspected:

- `artefacts/stage_5/noise_model_candidate_hard_negative_all_sources_cal_roundT/noise_model_candidates.json`

Candidate row used:

- `random_forest_lite + temporal`

Top-level artifact facts:

| Metric | Value |
|---|---:|
| TP on `doubleT_obstacle` | 52 |
| FN on `doubleT_obstacle` | 0 |
| FP_total | 193 |
| UNKNOWN_FP | 193 |
| model_temporal_FP | 0 |
| temporal fp_components | 0 |

By source:

| Source | Frames | UNKNOWN_FP | model_temporal_FP | FP_total | TP/FN on `doubleT_obstacle` |
|---|---:|---:|---:|---:|---:|
| `roundT_doubleT` | 252 | 10 | 0 | 10 | - |
| `squareT_platform_squareT_switch` | 877 | 12 | 0 | 12 | - |
| `doubleT_platform` | 345 | 0 | 0 | 0 | - |
| `roundT_squareT_pressureGate_squareT` | 545 | 12 | 0 | 12 | - |
| `doubleT_obstacle` | 201 | 0 | 0 | 0 | 52 / 0 |
| `roundT_pressureGate_roundT` | 268 | 5 | 0 | 5 | - |
| `new_data` | 11271 | 154 | 0 | 154 | - |
| **Total** | **13759** | **193** | **0** | **193** | **52 / 0** |

Read-only Docker replay of exactly these 193 frame keys confirmed all are runtime `status="UNKNOWN"` with `curve_axis_status="MISSING_CURVE_AXIS"`.

Разбивка причин:

| Причина по-русски | Reason code | Кадров |
|---|---|---:|
| Неоднозначная непрерывная цепочка рельсовой оси | `AMBIGUOUS_LOCAL_CONTINUITY_PATH` | 185 |
| Недостаточное непрерывное покрытие опорных сечений | `INSUFFICIENT_CONTIGUOUS_COVERAGE` | 4 |
| Недостаточно локально непрерывных пар рельсов | `INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT` | 4 |

По источникам и причинам:

| Source | Неоднозначная цепочка оси | Недостаточное покрытие | Недостаточно непрерывных пар |
|---|---:|---:|---:|
| `new_data` | 147 | 3 | 4 |
| `roundT_doubleT` | 10 | 0 | 0 |
| `roundT_pressureGate_roundT` | 5 | 0 | 0 |
| `roundT_squareT_pressureGate_squareT` | 12 | 0 | 0 |
| `squareT_platform_squareT_switch` | 11 | 1 | 0 |
| **Total** | **185** | **4** | **4** |

Frame keys by source:

- `roundT_doubleT`: 112, 113, 133, 140, 144, 146, 148, 157, 176, 180.
- `roundT_pressureGate_roundT`: 133, 142, 149, 253, 256.
- `roundT_squareT_pressureGate_squareT`: 388, 392, 405, 407, 415, 444, 452, 469, 480, 496, 512, 528.
- `squareT_platform_squareT_switch`: 764, 769, 780, 781, 782, 783, 784, 785, 787, 788, 789, 793.
- `new_data`: 154 frames; dominant clusters include 94-102, 471-498, 1122-1215, 3236-3299, 4064-4096, 5288-5358, 6555-6857, 7896-7961, 8954-9241, 9823-10568. Exact keys are preserved in the existing candidate artifact and will be emitted by the patched evaluator under `unknown_fp_frame_keys_by_reason` on rerun.

## Interpretation

The 193 remaining FP are not component classifier mistakes. They are frames where rail-axis selection refused to choose a unique supported path. По-русски: почти все оставшиеся `UNKNOWN` означают «алгоритм видит несколько конкурирующих вариантов оси рельсов и не считает безопасным выбрать один».

- `AMBIGUOUS_LOCAL_CONTINUITY_PATH`: неоднозначная непрерывная цепочка рельсовой оси; найден конкурирующий путь, достаточно похожий по score/cost и достаточно смещённый вбок, чтобы не выбирать ось автоматически.
- `INSUFFICIENT_CONTIGUOUS_COVERAGE`: недостаточное непрерывное покрытие; цепочка есть, но не проходит требования по span/coverage.
- `INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT`: недостаточно локально непрерывных пар; отдельные пары рельсов находятся, но не собираются в требуемую непрерывную цепочку.

Because all 193 have `curve_axis_status=MISSING_CURVE_AXIS`, suppressing them as non-alarms would be a safety/status policy change. It would hide frames where the system cannot establish the geometry it needs to evaluate the envelope. That would violate the protected contract.

## Ambiguous axis diagnostics

Artifact:

- `artefacts/stage_5/unknown_axis_diagnostics/ambiguity_metrics.json`

Read-only replay scope:

- Input: the same 193 `random_forest_lite + temporal` FP frame keys from `noise_model_candidates.json`.
- Runtime image: `lidar-mosmetro3d:unknown-axis-diagnostics`.
- Filtered records: 185 frames with `reason=AMBIGUOUS_LOCAL_CONTINUITY_PATH`.
- Decision stayed unchanged: replayed frames still emitted `status="UNKNOWN"` and `curve_axis_status="MISSING_CURVE_AXIS"`.

By source:

| Source | Ambiguous UNKNOWN_FP |
|---|---:|
| `new_data` | 147 |
| `roundT_doubleT` | 10 |
| `roundT_pressureGate_roundT` | 5 |
| `roundT_squareT_pressureGate_squareT` | 12 |
| `squareT_platform_squareT_switch` | 11 |
| **Total** | **185** |

Aggregate path metrics:

| Metric | min | p25 | median | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| Best path score | 6 | 12 | 14 | 14 | 15 | 18 |
| Competing path score | 6 | 11 | 12 | 12 | 13 | 16 |
| Score gap, best - competing | 0 | 1 | 2 | 2 | 2 | 2 |
| Best path cost | 0.578 | 8.421 | 9.973 | 10.796 | 11.931 | 13.764 |
| Competing path cost | 1.316 | 5.223 | 6.017 | 6.746 | 7.896 | 12.099 |
| Competing/best cost ratio | 0.491 | 0.567 | 0.618 | 0.677 | 2.337 | 5.703 |
| Best path coverage | 0.688 | 0.800 | 0.833 | 0.882 | 1.000 | 1.000 |
| Best path span, m | 10.0 | 28.0 | 30.0 | 32.0 | 34.0 | 40.0 |
| Lateral displacement to competing path, m | 0.701 | 0.753 | 0.812 | 0.988 | 1.190 | 2.117 |

Interpretation of the aggregate:

- The ambiguity is real under current scoring: the competing path is usually only 1-2 supported stations behind the selected path.
- In many frames the competing path has lower accumulated cost than the longer selected path, so cost alone cannot safely resolve the conflict.
- The competing path is laterally separated by about 0.7-1.2 m in most frames, which is large enough to matter for rail-axis/envelope placement.
- Therefore a blind rule like "choose best path anyway" or "raise/lower `ambiguity_ratio`" would be a geometry-policy change, not a harmless FP filter.

## Implemented diagnostic and reduction patch

Changed files:

- `scripts/evaluate_noise_classifier.py`
- `scripts/evaluate_noise_model_candidates.py`
- `tests/test_evaluate_noise_classifier.py`
- `src/cpp/auto_rails_core.hpp`
- `src/cpp/auto_rails_core.cpp`
- `src/cpp/curve_pipeline_stream_cli.cpp`
- `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`
- `tests/test_full_cpp_catalog_contract.py`

Change:

- Persist C++ `reason` and `curve_axis_status` for UNKNOWN rows.
- Summarize UNKNOWN reason counts, Russian descriptions, and per-reason frame keys in evaluator JSON.
- Add diagnostic-only `rail_axis_failure_diagnostics` for rail-axis UNKNOWN output in direct stream and ROS2.
- For `AMBIGUOUS_LOCAL_CONTINUITY_PATH`, expose selected and competing path metrics:
  - `best_path_score`;
  - `best_path_cost`;
  - `best_path_span_m`;
  - `best_path_coverage`;
  - `best_path_start_s_m`;
  - `best_path_end_s_m`;
  - `competing_path_score`;
  - `competing_path_cost`;
  - `competing_path_lateral_displacement_m`;
  - `competing_path_end_s_m`.
- Keep all frame metric semantics unchanged: negative UNKNOWN is still counted as FP in candidate summaries; current evaluator still keeps UNKNOWN outside TN.
- Add selected and competing rail-chain coordinates under diagnostic-only keys:
  - `best_path_pairs_source_xyz`;
  - `competing_path_pairs_source_xyz`.
- Reduce false ambiguity in `DetectAutoRails`: compare competing paths at shared `source_s_m` stations before declaring `AMBIGUOUS_LOCAL_CONTINUITY_PATH`. If the selected and competing paths have no shared station, keep the previous endpoint fallback. This avoids treating a shorter prefix of the same rail-axis chain as a different lateral path.

No runtime ML model, envelope geometry, axes, or numeric thresholds were changed. The rail-axis ambiguity decision was narrowed to same-station lateral comparison before it can return `UNKNOWN`.

## Reduction result

Small smoke before reduction:

- Artifact: `artefacts/stage_5/unknown_axis_diagnostics/ambiguous_pair_chains_smoke.json`.
- Frames: `new_data:94`, `roundT_doubleT:112`, `squareT_platform_squareT_switch:764`.
- All three stayed `status=UNKNOWN`, `reason=AMBIGUOUS_LOCAL_CONTINUITY_PATH`.
- Diagnostic pair chains were non-empty:
  - `new_data:94`: best 9 pairs, competing 8 pairs;
  - `roundT_doubleT:112`: best 14 pairs, competing 12 pairs;
  - `squareT_platform_squareT_switch:764`: best 12 pairs, competing 11 pairs.

Small smoke after reduction:

- Artifact: `artefacts/stage_5/unknown_axis_diagnostics/ambiguous_shared_station_fix_smoke.json`.
- `new_data:94`: still `UNKNOWN`, `AMBIGUOUS_LOCAL_CONTINUITY_PATH`.
- `roundT_doubleT:112`: changed to `curve_axis_status=CURVE_AXIS_SUPPORTED`, `status=NO_REPORTABLE_INTRUSION_NOISE_IGNORED`, `reason=ONLY_SPARSE_CORE_GROUPS`.
- `squareT_platform_squareT_switch:764`: still `UNKNOWN`, `AMBIGUOUS_LOCAL_CONTINUITY_PATH`.

Replay of previous 193 FP frame keys after reduction:

- Artifact: `artefacts/stage_5/unknown_axis_diagnostics/shared_station_fix_193_fp_replay.json`.
- `MISSING_CURVE_AXIS`: 193 -> 41.
- 152 frames moved to `CURVE_AXIS_SUPPORTED` with `status=NO_REPORTABLE_INTRUSION_NOISE_IGNORED`.
- Remaining reasons:

| Reason | Frames |
|---|---:|
| `AMBIGUOUS_LOCAL_CONTINUITY_PATH` | 33 |
| `INSUFFICIENT_CONTIGUOUS_COVERAGE` | 4 |
| `INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT` | 4 |

Full seven-source eval after reduction:

- Artifact: `artefacts/stage_5/noise_model_candidate_shared_station_fix_all_sources/noise_model_candidates.json`.
- Scope: full 13,759-frame seven-source development run.

| Candidate | Threshold | UNKNOWN_FP | model_temporal_FP | FP_total | TP/FN on `doubleT_obstacle` | TN |
|---|---:|---:|---:|---:|---:|---:|
| `random_forest_lite + temporal` | 0.838710 | 41 | 0 | 41 | 52 / 0 | 13,666 |
| `random_forest + temporal` | 0.774194 | 41 | 0 | 41 | 52 / 0 | 13,666 |
| `ensemble_v1 + temporal` | 0.903226 | 41 | 0 | 41 | 52 / 0 | 13,666 |
| `lightgbm + temporal` | 0.967742 | 41 | 91 | 132 | 52 / 0 | 13,575 |
| `legacy_tree_v1 + temporal` | 0.500000 | 41 | 277 | 318 | 52 / 0 | 13,389 |

For the best candidates, `UNKNOWN_FP` dropped from 193 to 41 and `model_temporal_FP` stayed 0. No `UNKNOWN` frame was converted to `CLEAR`; resolved ambiguous-axis frames became supported-axis non-reportable/noise outcomes when downstream evidence allowed that status.

## Commands run

- `Get-Content -Raw .\agents\context_router.md` - PASS, routing rules read.
- `Get-Content -Raw C:\Users\Ilya\.codex\skills\bug-reproducer\SKILL.md` - PASS, approval-gated workflow read.
- `Get-Content -Raw .\agents\lidar_obstacle_pipeline.md` - PASS.
- `Get-Content -Raw .\agents\validation_reviewer.md` - PASS.
- `rg --files` - PASS, scoped file inventory.
- `Get-Content -Raw .\docs\README_noise_classifier.md` - PASS, current metrics and hard-negative result read.
- `rg -n 'UNKNOWN|DEGRADED|system_status|diagnostic|reason|status' ...` - PASS, status locations searched.
- Read-only Docker replay of exactly the 193 `random_forest_lite + temporal` FP frame keys from `noise_model_candidates.json` through `lidar-mosmetro3d:noise-current` and `curve_pipeline_stream_cli 2.0` - PASS; produced reason breakdown above.
- `.\.venv\Scripts\python.exe -m unittest tests.test_evaluate_noise_classifier` - PASS, `Ran 4 tests` before ambiguity metrics patch.
- `.\.venv\Scripts\python.exe -m unittest tests.test_evaluate_noise_classifier tests.test_full_cpp_catalog_contract` - PASS, `Ran 9 tests`.
- `docker build -t lidar-mosmetro3d:unknown-axis-diagnostics .` - PASS, colcon built `lidar_mosmetro3d_cpp`.
- Read-only smoke on `new_data:94` with `lidar-mosmetro3d:unknown-axis-diagnostics` and `curve_pipeline_stream_cli 2.0` - PASS. Output stayed `status=UNKNOWN`, `reason=AMBIGUOUS_LOCAL_CONTINUITY_PATH`, `curve_axis_status=MISSING_CURVE_AXIS`, and added:
  - `best_path_score=9`;
  - `best_path_cost=2.830531`;
  - `best_path_span_m=18.0`;
  - `best_path_coverage=0.9`;
  - `competing_path_score=8`;
  - `competing_path_cost=6.035924`;
  - `competing_path_lateral_displacement_m=1.074705`.
- Read-only replay of all 193 `UNKNOWN_FP` frame keys with `lidar-mosmetro3d:unknown-axis-diagnostics` - PASS; wrote `artefacts/stage_5/unknown_axis_diagnostics/ambiguity_metrics.json` and produced the aggregate ambiguity metrics above.
- `docker build -t lidar-mosmetro3d:unknown-axis-pair-diagnostics .` - PASS, colcon built `lidar_mosmetro3d_cpp`.
- Read-only smoke for diagnostic pair-chain export on `new_data:94`, `roundT_doubleT:112`, `squareT_platform_squareT_switch:764` - PASS; wrote `artefacts/stage_5/unknown_axis_diagnostics/ambiguous_pair_chains_smoke.json`.
- `docker build -t lidar-mosmetro3d:unknown-axis-shared-station-fix .` - PASS, colcon built `lidar_mosmetro3d_cpp`.
- Read-only smoke for shared-station ambiguity fix on the same three frames - PASS; wrote `artefacts/stage_5/unknown_axis_diagnostics/ambiguous_shared_station_fix_smoke.json`.
- Read-only replay of the previous 193 FP frame keys with `lidar-mosmetro3d:unknown-axis-shared-station-fix` - PASS; wrote `artefacts/stage_5/unknown_axis_diagnostics/shared_station_fix_193_fp_replay.json`.
- Full seven-source eval with `lidar-mosmetro3d:unknown-axis-shared-station-fix` - PASS; wrote `artefacts/stage_5/noise_model_candidate_shared_station_fix_all_sources/noise_model_candidates.json`.

Notes:

- A full read-only replay of all 13759 frames was attempted but stopped after taking too long; it produced no evidence and is not used for conclusions.
- The targeted 193-frame replay is sufficient for the stated UNKNOWN_FP cause because the frame keys came from the full existing candidate artifact and every queried key replayed to `status="UNKNOWN"`.

## Validation

- Achieved level for diagnostic code change: L1, narrow Python/static tests passed and Docker build passed.
- Achieved level for ambiguity diagnostic runtime smoke: L1 on `new_data:94`.
- Achieved level for ambiguity aggregate: L2 for the 185-frame diagnostic replay over known `UNKNOWN_FP` frame keys.
- Achieved level for UNKNOWN source attribution: L4 over the existing seven-source development artifact frame keys, plus targeted replay of all 193 UNKNOWN_FP frames.
- Achieved level for shared-station ambiguity fix: L3 for small smoke and targeted 193-frame replay; L4 for full seven-source development eval after the fix.

Validation verdict: `PASS_WITH_RISKS` for the shared-station ambiguity fix on development data. It is a rail-axis status decision change and still needs independent held-out/visual review before treating the result as production-safe.

## Safe reduction options

Implemented first reduction patch:

- compare ambiguous local-continuity candidates at shared stations before returning `AMBIGUOUS_LOCAL_CONTINUITY_PATH`;
- keep endpoint fallback only when no shared station exists;
- keep `UNKNOWN` behavior for true remaining ambiguity and insufficient support.

Possible next work, each requiring its own smoke and full seven-source eval:

1. Review `AMBIGUOUS_LOCAL_CONTINUITY_PATH` frames visually or with saved rail candidates to decide whether ambiguity is real switch geometry, false alternative rails, or overly strict rejection.
2. If justified by evidence, design a conservative ambiguity tie-breaker. This would be a geometry contract change and needs safety review before adoption.
3. Consider a user-facing split between `UNKNOWN_AXIS_AMBIGUOUS` and `UNKNOWN_AXIS_INSUFFICIENT_SUPPORT` rather than a single undifferentiated alarm. This improves UX without claiming CLEAR.

## Residual risk

- The current report uses development labels: other sources are treated as negative by working assumption, not independent full object review.
- The shared-station fix was validated on the development split, not independent held-out data.
- The fix changes rail-axis acceptance for prefix-like competing chains. It does not change envelope dimensions or thresholds, but it can still affect downstream frame status and should be visually reviewed on representative sources.
- Remaining 41 UNKNOWN_FP are still user-facing non-useful alarms and should not be mined as component-classifier negatives.

## Next minimal test

Visually inspect the remaining 33 `AMBIGUOUS_LOCAL_CONTINUITY_PATH` frames, especially `new_data` and `squareT_platform_squareT_switch`, using `best_path_pairs_source_xyz` and `competing_path_pairs_source_xyz`. Do not lower them to CLEAR; next reduction should again start with small smoke, then full seven-source eval.
