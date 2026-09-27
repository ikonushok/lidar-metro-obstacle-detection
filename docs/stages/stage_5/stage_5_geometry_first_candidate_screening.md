# Stage 5: geometry-first candidate screening

Дата: 2026-09-25. Режим: `inspect/calibration/validation`.

## Задача

- Goal: разработать и проверить offline geometry-first / hybrid detector candidate для `cloud_with_fake_obj` и regression на `doubleT_obstacle` через существующую event-level линейку.
- Наблюдаемая проблема или исходный claim: raw CORE `>=1000` ловит 6/6 localized positives в `cloud_with_fake_obj`, но даёт boundary FP на object #7 `630..633`.
- Non-goals: не интегрировать candidate в C++/ROS2 runtime; не менять temporal policy, runtime thresholds, envelope, safety contracts, ROS messages, ML weights; не делать push/commit.
- Source of truth: `docs/stages/stage_5/cloud_with_fake_obj_working_labels.json`, `scripts/evaluate_working_obstacle_labels.py`, raw CORE audit `artefacts/stage_5/cloud_with_fake_obj_raw_core_60m_20260925/`.
- Пункт/раздел ТЗ и обязательный результат: offline development evidence, не runtime readiness claim.
- Этап docs/README_work_plan.md: stage 5 detector candidate/evaluation.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: локальная Windows workspace и сохранённые JSON-артефакты, при необходимости существующий C++ stream CLI.
- Входные данные и единицы: component rows with `point_count`, `min_s_m`, `max_s_m`, `nearest_distance_m`, `centroid_xyz`, `extent_xyz_m`, metres.
- Конкретный bag/версия/интервал, топик и объём выборки: `cloud_with_fake_obj` frames 0..1509 from saved audit; `doubleT_obstacle` frames 0..200 or existing extracted bag/player.
- Факты из docs/README_dataset_audit.md, подтверждения на текущем входе и непроверенные предположения: `cloud_with_fake_obj` is development benchmark after organizer disclosure; `doubleT_obstacle` is project regression, not independent held-out.
- Рабочие frames и направление transforms: no new transforms; uses existing raw CORE audit in source XYZ and projected `s`.
- Режим baseline/расширений; необходимые TF/движение/карта/габарит и поведение при их отсутствии: offline screening over already extracted CORE components; UNKNOWN is not CLEAR.
- Временная база событий и способ измерения вычислительной задержки: frame-index event matching only; no runtime latency claim.
- Allowed files: new/updated offline helper script under `scripts/`, new artifacts under `artefacts/stage_5/geometry_first_candidate_20260925/`, this report.
- Files to avoid: C++ runtime, ROS2 launch/config/message files, existing stage reports except references.
- Защищённые контракты: `UNKNOWN != CLEAR`; object outside/above core-gabarit is not target obstacle; no runtime safety decision from offline candidate.
- Deliverables и статус каждого: analysis done; candidate rules checked; evaluator outputs saved; doubleT regression checked and explicitly failed for the standalone cloud gate; final report done.
- Путь отчёта этапа или категории: `docs/stages/stage_5/stage_5_geometry_first_candidate_screening.md`.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer` и почему: да, как отдельный проход по offline geometry thresholds and boundary handling before final claim.
- Нужен ли отдельный этап `validation_reviewer`; порядок и кто выполняет проходы: да, после выполнения команд проверить evidence/claims.
- Validation target: L1 for saved JSON/evaluator outputs; L2-like static consistency for report only, no runtime quality claim.
- Validation method: compare event metrics for candidate rules on `cloud_with_fake_obj`; run same evaluator on `doubleT_obstacle`; inspect component feature summaries for positives vs boundary #7.
- Acceptance criteria: keep 6/6 localized positives on `cloud_with_fake_obj`; remove or classify object #7 as boundary/warning, not obstacle; keep `doubleT_obstacle` 52/52 frames or explicitly report failure.
- Stop conditions: required artifacts missing and cannot be regenerated locally; rule would require protected runtime/envelope/temporal changes; evidence contradicts 6/6 or doubleT regression claim.

## Разбор raw CORE FP на object #7

Raw CORE `>=1000` ловит boundary object #7, потому что у внешнего `2x2` объекта в кадрах `630..633` видна плотная вертикальная грань, пересекающая текущую raw CORE selection по принятой оси/габариту. Это не слабый шум: top components имеют `point_count=1044..3404`.

Главное отличие #7 от target positives:

| Event | Класс | Top component evidence |
|---|---|---|
| #1 `2x2 center` | target | `point_count=1442..2862`, `centroid_x≈0`, `extent_x≈1.95..1.98`, `extent_z≈1.65..1.75` |
| #2 `small center` | target | best frame `368`: `point_count=1550`, `centroid_x=-0.02`, `extent=(0.34,0.28,0.30)` |
| #3 `small on rails` | target | best frame `479`: `point_count=1254`, `centroid_x=0.98`, `extent=(0.29,0.07,0.29)` |
| #4 `small edge inside` | target | frames `531..532`: `point_count=1032`, `centroid_x=-1.26`, `extent_x=0.293`, `extent_z=0.30` |
| #6 `2x2 edge inside` | target | `point_count=1458..3827`, `centroid_x≈+1.13`, `extent_x=0.41..0.66`, `extent_z=1.93..2.13` |
| #9 `long low on rails` | target | `point_count=1014..1134`, `centroid_x=1.38..1.58`, `extent_y=12..14`, `extent_z≈0.25..0.29` |
| #7 `2x2 outside` | boundary | `point_count=1044..3404`, `centroid_x=-1.32..-1.38`, `extent_x=0.14..0.22`, `extent_z=1.95..2.00` |

Вывод: #7 — high-support, но left thin tall boundary face. Простое правило `point_count>=1000` не различает edge-inside и outside-left boundary; нужен boundary/warning branch.

Полный JSON: `artefacts/stage_5/geometry_first_candidate_20260925/cloud_feature_comparison.json`.

## Проверенные rules

1. `raw_core_ge1000`: любой raw CORE component с `point_count >= 1000`.
   - Cloud: 6/6 localized positives, но #7 boundary FP.
   - DoubleT: 0/52 positive frames, полный провал.

2. `geometry_boundary_suppressed_obstacle_ge1000`: `raw_core_ge1000`, кроме компонентов с `centroid_x < -1.30`, `extent_x < 0.25`, `extent_z > 1.50`; такие компоненты переводятся в `geometry_boundary_warning_ge1000`.
   - Cloud: 6/6 localized positives, #7 уходит в boundary warning `630..633`, 0/1 localized boundary FP, 26 alarm frames, 1 unassigned alarm (`244`).
   - DoubleT: 0/52, потому что компоненты doubleT меньше 1000 points.

3. `geometry_hybrid_obstacle_ge250`: lower-support compact/low-long/tall-overlap geometry at `point_count >= 250`, with the same boundary warning rule.
   - Cloud: 6/6 localized positives, но #7 снова FP и 648 unassigned alarms.
   - DoubleT: event-level hit есть, но strict frame regression only 36/52, плюс 87 outside-window alarms.

## Результаты evaluator

Артефакты:

- `artefacts/stage_5/geometry_first_candidate_20260925/cloud_with_fake_obj_ge1000_eval.json`
- `artefacts/stage_5/geometry_first_candidate_20260925/cloud_with_fake_obj_ge250_eval.json`
- `artefacts/stage_5/geometry_first_candidate_20260925/doubleT_obstacle_ge1000_eval.json`
- `artefacts/stage_5/geometry_first_candidate_20260925/doubleT_obstacle_ge250_eval.json`
- `artefacts/stage_5/geometry_first_candidate_20260925/metric_summary.json`
- `artefacts/stage_5/geometry_first_candidate_20260925/doubleT_frame_regression.json`

Summary:

| Rule | Cloud localized positives | Cloud #7 boundary FP | Cloud unassigned alarms | DoubleT event hit | DoubleT strict frames |
|---|---:|---:|---:|---:|---:|
| `raw_core_ge1000` | 6/6 | 1/1 | 1 | no | 0/52 |
| `geometry_boundary_suppressed_obstacle_ge1000` | 6/6 | 0/1 | 1 | no | 0/52 |
| `geometry_hybrid_obstacle_ge250` | 6/6 | 1/1 | 603 | yes | 36/52, 87 outside alarms |

## Recommendation

Best offline screening candidate for `cloud_with_fake_obj`: `geometry_boundary_suppressed_obstacle_ge1000` plus explicit `geometry_boundary_warning_ge1000`.

It solves the stated cloud boundary issue without training on `cloud_with_fake_obj` as independent test: 6/6 localized positives are retained and object #7 becomes boundary/warning, not obstacle. It is not sufficient as a standalone detector for `doubleT_obstacle`.

For a project candidate that preserves doubleT, use a hybrid cascade only at screening level:

- keep the already checked `model_v1 + temporal`/current temporal path for small-support doubleT-style positives (`52/52`, from `artefacts/stage_5/noise_model_candidate_ml_by_source/doubleT_obstacle/noise_model_candidates.json`);
- add `geometry_boundary_suppressed_obstacle_ge1000` as a high-support geometry branch for the cloud development benchmark;
- keep `geometry_boundary_warning_ge1000` separate from obstacle alarms.

This should not be integrated into C++/ROS2 runtime without a separate task, because it introduces geometry thresholds and boundary semantics that need negative cases #5/#8, object #10 localization, and independent non-development validation.

## Geometry-first gate + ML suppressor pass

После уточнения направления выбран вариант `geometry-first safety gate + ML suppressor`:

- strong geometry gate: `point_count >= 1000`, кроме explicit left-thin-tall boundary rule;
- boundary warning: `centroid_x < -1.30`, `extent_x < 0.25`, `extent_z > 1.50`;
- ML suppressor: shallow tree only for uncertain components `250..999 points`; ML не имеет права удалить strong geometry-positive.

Новый скрипт: `scripts/screen_geometry_gate_ml_suppressor.py`.

Артефакты:

- `artefacts/stage_5/geometry_gate_ml_suppressor_20260925/cloud_train_apply/`
- `artefacts/stage_5/geometry_gate_ml_suppressor_20260925/cloud_train_apply_event_eval.json`
- `artefacts/stage_5/geometry_gate_ml_suppressor_20260925/doubleT_apply_cloud_model/`
- `artefacts/stage_5/geometry_gate_ml_suppressor_20260925/doubleT_apply_cloud_model_event_eval.json`

Training/calibration:

- training rows from cloud weak event labels: `694` uncertain components;
- class counts: `50` positive-window, `644` negative/background/boundary;
- selected threshold: `1.0`;
- interpretation: allowing uncertain ML components increased risk more than benefit, so calibrated suppressor lets through no uncertain components.

Cloud result:

| Detector | Localized cloud positives | #7 boundary FP | Alarm frames | Unassigned alarms |
|---|---:|---:|---:|---:|
| `geometry_gate_obstacle` | 6/6 | 0/1 | 26 | 1 |
| `ml_uncertain_obstacle` | 0/6 | 0/1 | 0 | 0 |
| `geometry_gate_ml_suppressor_obstacle` | 6/6 | 0/1 | 26 | 1 |
| `geometry_boundary_warning` | not obstacle | marks #7 | 9 | 5 |

DoubleT sanity using the cloud-trained suppressor:

- `geometry_gate_ml_suppressor_obstacle`: `0/52` strict positive frames.
- This is expected for this branch: doubleT components are below the cloud strong-gate scale and the cloud-trained suppressor is conservative.
- Conclusion: this branch is a cloud synthetic candidate, not a universal replacement for the existing doubleT path.

Decision after this pass:

- Keep `geometry_gate_ml_suppressor_obstacle` as the current best cloud-focused offline candidate.
- Do not claim ML improves cloud yet; current selected ML suppressor mainly prevents lower-support uncertain components from adding FP.
- Keep doubleT as regression/sanity only; preserving doubleT requires either the existing temporal/model path or a separate small-support branch, not this cloud gate alone.

## Отчёт о завершении

- Что изменено: добавлены offline helpers `scripts/screen_geometry_first_candidate.py`, `scripts/summarize_geometry_first_candidate.py`, `scripts/screen_geometry_gate_ml_suppressor.py`, `scripts/localize_cloud_synthetic_objects.py`, `scripts/render_cloud_boundary_visual_confirm.py`; созданы артефакты в `artefacts/stage_5/geometry_first_candidate_20260925/`, `artefacts/stage_5/geometry_gate_ml_suppressor_20260925/`, `artefacts/stage_5/cloud_boundary_localization_probe_20260925/`, `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/`; runtime/C++/ROS2 не изменялись.
- Evidence inspected: working labels, evaluator, raw CORE cloud audit, newly generated doubleT raw CORE audit, saved doubleT `model_v1 + temporal` metric summary.
- Commands run:
  - `python scripts/screen_geometry_first_candidate.py ... --min-points 1000/250` for cloud and doubleT.
  - `python scripts/evaluate_working_obstacle_labels.py ...` for cloud/doubleT ge1000/ge250.
  - `docker run --rm ... python3 scripts/audit_geometric_core_cloud.py ... doubleT_obstacle ...` completed, 201 frames processed.
  - `python scripts/summarize_geometry_first_candidate.py ...` completed.
  - `python scripts/screen_geometry_gate_ml_suppressor.py ...` for cloud train/apply and doubleT apply completed.
  - `python scripts/evaluate_working_obstacle_labels.py ...` for gate+ML cloud/doubleT completed.
- Validation level achieved: L1 for offline JSON/evaluator outputs; no runtime validation claim.
- Что не проверено: #5/#8 localization, #10 localization, independent held-out positive transfer, ROS2 runtime behavior, C++ integration.
- Известные FP/FN или safety-риски: cloud ge1000 candidate leaves one unassigned alarm at frame `244`; pure geometry rules fail doubleT strict regression; lower-support ge250 creates many alarms and does not remove #7.
- Safety geometry pass: no protected runtime/envelope/temporal contract changed; `UNKNOWN != CLEAR` preserved; #7 is warning/boundary, not `CLEAR`.
- Validation pass: claims are limited to saved offline artifacts; `cloud_with_fake_obj` is development benchmark, not independent held-out.
- Следующий минимальный тест: localize #5/#8/#10 and evaluate the ge1000 boundary warning branch against those windows before any runtime design.
- Residual risk: thresholds are development-calibrated from known cloud/doubleT artifacts and may encode axis/envelope quirks rather than object semantics.

## Boundary localization probe for #5/#8/#10

Дополнительный проход после уточнения цели: не ловить все объекты как obstacle, а доказать разделение `target obstacle` vs `outside/above boundary`.

Новый helper: `scripts/localize_cloud_synthetic_objects.py`.

Артефакты:

- `artefacts/stage_5/cloud_boundary_localization_probe_20260925/localization_summary.json`
- `artefacts/stage_5/cloud_boundary_localization_probe_20260925/cloud_with_fake_obj_localization_probe_labels.json`
- `artefacts/stage_5/cloud_boundary_localization_probe_20260925/gate_ml_upper_warning_cloud/`
- `artefacts/stage_5/cloud_boundary_localization_probe_20260925/gate_ml_upper_warning_cloud_eval.json`
- `artefacts/stage_5/cloud_boundary_localization_probe_20260925/gate_ml_upper_warning_doubleT_eval.json`

Localization evidence:

| Object | Organizer class for obstacle detection | Probe result | Decision |
|---|---|---|---|
| #5 `small outside close` | `negative_boundary` | no stable compact outside-close raw CORE run in `533..578`; previous broad heuristic matched #6 ramp-up shape and was rejected | keep `frame_interval=null`, unscorable |
| #8 `2x2 above` | `negative_boundary` | tentative upper/above raw CORE run `674..681`; best component `point_count=850`, `centroid_z≈2.05`, `extent≈(2.41, 1.92, 0.84)` | scorable `negative_boundary`, not obstacle |
| #10 `narrow hanging` | positive only if CORE-intersection confirmed | no narrow hanging CORE-intersection run in `1157..1509` | keep `frame_interval=null`, positive unlocalized/unscorable |

Candidate rule update for offline screening only:

- boundary warning now includes #7 outside-left thin/tall rule and #8 upper/above broad rule;
- `geometry_boundary_warning` is not an obstacle alarm;
- `geometry_gate_ml_suppressor_obstacle` suppresses those boundary-warning components before obstacle scoring.

Probe eval with localized #8:

| Detector | Cloud positives | Positive unlocalized | Boundary obstacle FP | Boundary scorable | Obstacle alarms | Unassigned obstacle alarms |
|---|---:|---:|---:|---:|---:|---:|
| `geometry_gate_ml_suppressor_obstacle` | 6/6 | 1 (#10) | 0 | 2 (#7/#8) | 26 | 1 |

Warning evidence:

- `geometry_boundary_warning` runs: `625..633` (#7 area) and `675..681` (#8 area).
- If warning is scored as an alarm by the generic evaluator, it appears as expected `negative_boundary` FP; this is not an obstacle FP because warning is a separate non-obstacle state.

DoubleT sanity with the same cloud-trained branch:

- `geometry_gate_ml_suppressor_obstacle`: `0/1` event, `0` alarm frames.
- Interpretation unchanged: this cloud geometry gate is not a replacement for the existing doubleT path.

## Visual confirmation of #8

После localization probe выполнена visual-only проверка raw PointCloud2 кадров из `dataset/extracted/cloud_with_fake_obj`.

Новый helper: `scripts/render_cloud_boundary_visual_confirm.py`.

Команда:

```text
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage-4-cpu-viewer-v2-best bash -lc "python3 scripts/render_cloud_boundary_visual_confirm.py --bag-dir /workspace/dataset/extracted/cloud_with_fake_obj --components /workspace/artefacts/stage_5/cloud_with_fake_obj_raw_core_60m_20260925/components.json --output-dir /workspace/artefacts/stage_5/cloud_boundary_visual_confirm_20260925 --frames 631 633 674 675 678 681 682 --point-limit 50000"
```

Artifacts:

- `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/visual_confirm_summary.json`
- `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/frame_00675_raw_component_views.png`
- `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/frame_00678_raw_component_views.png`
- `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/frame_00681_raw_component_views.png`
- `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/gate_ml_working_labels_cloud_eval.json`

Visual result:

- #8 has a visible upper/above component in frames `674..681`.
- Representative components:
  - frame `675`: `point_count=259`, `centroid_z=2.18`, `extent_z=0.85`;
  - frame `678`: `point_count=574`, `centroid_z=2.12`, `extent=(2.41, 1.93, 0.89)`;
  - frame `681`: `point_count=702`, `centroid_z=1.86`, `extent=(2.39, 1.92, 0.67)`.
- The component is visually separated above the lower/core layer in X/Z and Y/Z projections.
- Decision: #8 is `negative_boundary`, not `positive_target`.

Working labels update:

- `docs/stages/stage_5/cloud_with_fake_obj_working_labels.json`: #8 now has `frame_interval=[674,681]`, `matching_status=visual_confirmed_raw_core_boundary_check`.
- #5 remains `frame_interval=null`.
- #10 remains `frame_interval=null` and unlocalized/unscorable.

Eval after updating working labels:

| Detector | Cloud positives | Positive unlocalized | Boundary obstacle FP | Boundary scorable | Obstacle alarms | Unassigned obstacle alarms |
|---|---:|---:|---:|---:|---:|---:|
| `geometry_gate_ml_suppressor_obstacle` | 6/6 | 1 (#10) | 0 | 2 (#7/#8) | 26 | 1 |

Boundary warning evidence:

- `geometry_boundary_warning`: 16 frames total.
- Runs: `625..633` (#7 area), `675..681` (#8 area).
- Warning remains a non-obstacle state; generic event evaluator will count it as negative-boundary alarm if evaluated as an obstacle detector, which is intentionally not how this field is used.

## Full-cloud scan for #10

Goal: попытаться локализовать `cloud_fake_obj_10_narrow_hanging` не через raw CORE, а через полный `PointCloud2`, потому что CORE-компоненты не дали уверенного окна.

Новый helper: `scripts/scan_cloud_hanging_candidates.py`.

Commands:

```text
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage-4-cpu-viewer-v2-best bash -lc "python3 scripts/render_cloud_boundary_visual_confirm.py --bag-dir /workspace/dataset/extracted/cloud_with_fake_obj --components /workspace/artefacts/stage_5/cloud_with_fake_obj_raw_core_60m_20260925/components.json --output-dir /workspace/artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/sample_frames --frames 1157 1200 1250 1300 1350 1400 1450 1500 --point-limit 60000"
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage-4-cpu-viewer-v2-best bash -lc "python3 scripts/scan_cloud_hanging_candidates.py --bag-dir /workspace/dataset/extracted/cloud_with_fake_obj --output /workspace/artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/hanging_candidate_scan.json --frame-start 1157 --frame-end 1509"
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage-4-cpu-viewer-v2-best bash -lc "python3 scripts/scan_cloud_hanging_candidates.py --bag-dir /workspace/dataset/extracted/cloud_with_fake_obj --output /workspace/artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/hanging_candidate_scan_wide.json --frame-start 1157 --frame-end 1509 --abs-x-max 1.80 --z-min 0.00 --z-max 2.90 --voxel-size 0.10"
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage-4-cpu-viewer-v2-best bash -lc "python3 scripts/render_cloud_boundary_visual_confirm.py --bag-dir /workspace/dataset/extracted/cloud_with_fake_obj --components /workspace/artefacts/stage_5/cloud_with_fake_obj_raw_core_60m_20260925/components.json --hanging-scan /workspace/artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/hanging_candidate_scan_wide.json --output-dir /workspace/artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/candidate_frames_overlay --frames 1481 1486 1489 1496 1500 --point-limit 70000"
```

Artifacts:

- `artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/sample_frames/`
- `artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/hanging_candidate_scan.json`
- `artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/hanging_candidate_scan_wide.json`
- `artefacts/stage_5/cloud_hanging_obj10_visual_scan_20260925/candidate_frames_overlay/`

Results:

- Strict central scan `|x|<=1.10`, `z>=0.20`, frames `1157..1509`: `0` candidate frames.
- Wider scan `|x|<=1.80`, `z>=0.00`: `63` candidate frames, but top runs are edge/side structures:
  - strongest run `1485..1501`;
  - examples: `x≈+1.50` or `x≈-1.75`, visually aligned with side wall/infrastructure, not central core.
- Overlay visuals for frames `1486`, `1489`, `1496` show dashed magenta hanging-scan candidates at side/edge infrastructure, not as a confirmed central CORE-positive obstacle.

Decision:

- #10 is not localized as a CORE-positive target in this pass.
- `cloud_fake_obj_10_narrow_hanging` remains `frame_interval=null`, `positive_target` but unscorable.
- Working label note updated to record: full-cloud scan found no confirmed central CORE-positive hanging candidate.
