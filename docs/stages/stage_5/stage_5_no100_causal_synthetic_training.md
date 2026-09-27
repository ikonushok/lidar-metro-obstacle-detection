# Stage 5: no100 causal synthetic training

## Задача

- Goal: обучить кандидаты `random_forest`, `gradient_boosting`, `lightgbm` на актуальном C++ pipeline с synthetic train `10/30/60 м` и сравнить их против фиксированного `candidate_baseline_v2 + causal_runtime`.
- Наблюдаемая проблема или исходный claim: 100 м не даёт пригодных CORE-positive компонентов на текущем лидаре, поэтому 100 м исключён из train и сохраняется как documented limitation.
- Non-goals: не менять ROS2 temporal policy, runtime thresholds, envelope, C++ runtime model, safety contracts; не использовать `legacy_adjacent`; не использовать real test для training/hard-negative mining/threshold selection.
- Source of truth: запрос пользователя 2026-09-25, `config/stage_5_real_synthetic_no100_causal_experiment.yaml`, актуальный `HEAD`.
- Этап docs/README_work_plan.md: stage 5 experiments/metrics.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: fresh local Docker image from current source.
- Входные данные и единицы: source-frame XYZ metres; current CORE components from fresh C++ stream.
- Конкретный bag/версия/интервал: synthetic train from `doubleT_obstacle` frames 0-7; real hard-negative/calibration from `new_data [0,600)`; real eval on `new_data [600,end)` plus other real sources; `doubleT_obstacle 13-64` as known positive regression.
- Рабочие frames и направление transforms: `lidar_livox <- lidar_livox` for synthetic train; no 100 m extrapolation claim.
- Режим baseline/расширений: fixed `candidate_baseline_v2 + causal_runtime`; same temporal for all candidates.
- Allowed files: focused evaluator/generator scripts, config, this report, tests, `artefacts/stage_5/`.
- Files to avoid: ROS2 temporal policy/runtime, envelope geometry, C++ thresholds, runtime model integration.
- Защищённые контракты: `UNKNOWN != CLEAR`; test never used for training/tuning; 100 m not used as positive train; no old component rows.
- Deliverables и статус каждого:
  - versioned config: implemented;
  - synthetic no100 manifest: implemented;
  - trained candidate artifacts: implemented;
  - real causal comparison metrics: implemented;
  - final/rejected decision: rejected for runtime replacement.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer`: нет, geometry/runtime contracts не меняются.
- Нужен ли validation reviewer: да как validation-style pass перед claim о качестве.
- Validation target: L1 for scripts/tests, L3/L4 for replay metrics if full run completes.
- Validation method: unit tests, Docker build, synthetic generation, causal real eval with explicit train/test windows.
- Acceptance criteria: candidate reduces real FP vs `candidate_baseline_v2 + causal_runtime`, preserves `52/52`, does not critically regress low/thin synthetic slices; otherwise save as rejected/no runtime integration.
- Stop conditions: any test leakage, missing fresh C++ replay, no trainable synthetic positives, need to change temporal/envelope/runtime thresholds.

## Отчёт о выполнении

- Что изменено: добавлен no100/causal протокол, synthetic train без 100 м, real evaluator получил synthetic component rows, фиксированный `candidate_baseline_v2`, ограничение hard-negative/calibration окнами development и eval cut `new_data >=600`.
- Evidence inspected:
  - `config/stage_5_real_synthetic_no100_causal_experiment.yaml`;
  - `artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_no100_causal_train_v1_20260925/generation_summary.json`;
  - `artefacts/stage_5/no100_causal_real_synthetic_v1_20260925/noise_model_candidates.json`;
  - `artefacts/stage_5/no100_causal_real_synthetic_v1_20260925/compact_summary.json`.
- Commands run:
  - `docker build --progress plain -t lidar-mosmetro3d:stage5-no100-causal .` - PASS, C++ package rebuilt.
  - `docker run ... python3 -m py_compile scripts/evaluate_noise_model_candidates.py scripts/build_synthetic_recall_dataset.py scripts/evaluate_synthetic_noise_model_candidates.py` - PASS.
  - `docker run ... python3 -m unittest tests.test_evaluate_noise_classifier tests.test_build_synthetic_recall_dataset tests.test_synthetic_obstacle_generator` - PASS, 22 tests.
  - `docker run ... scripts/build_synthetic_recall_dataset.py ... --distance-m 10 --distance-m 30 --distance-m 60 --split-policy all_train` - PASS, `864` placements.
  - `docker run ... scripts/evaluate_noise_model_candidates.py ... --temporal-mode causal_runtime --hard-negative-max-duration-seconds 600 --synthetic-component-rows ... --calibration-max-duration-seconds 600 --eval-source-min-offset new_data:600` - PASS.
  - `docker run ... scripts/summarize_noise_model_eval.py ...` - PASS, compact summary saved.
- Synthetic no100 train summary:
  - placements: `864`;
  - component rows: `118093`;
  - positive CORE components: `925`;
  - visibility failures are recorded in generation summary;
  - 100 m excluded and not used as train/recall evidence.
- Real causal evaluation summary:

| Candidate | Threshold | UNKNOWN FP | Model temporal FP | FP total | TP | FN | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| `candidate_baseline_v2` | 0.806452 | 23 | 0 | **23** | 51 | 1 | keep current baseline |
| `ensemble_v1` | 0.935484 | 23 | 12 | 35 | **52** | **0** | rejected: FP worse than baseline |
| `random_forest` | 0.903226 | 23 | 19 | 42 | **52** | **0** | rejected: FP worse than baseline |
| `random_forest_lite` | 0.903226 | 23 | 120 | 143 | **52** | **0** | rejected |
| `gradient_boosting` | 0.903226 | 23 | 657 | 680 | **52** | **0** | rejected |
| `lightgbm` | 0.935484 | 23 | 1267 | 1290 | **52** | **0** | rejected |

- Decision: no candidate replaces `candidate_baseline_v2`. New models restore `52/52` on known positive regression, but none reduces real FP relative to the fixed current baseline. No C++/ROS2 runtime integration is allowed from this experiment.
- Validation level achieved: L3 for offline Docker replay/evaluator evidence on the stated real/synthetic splits; L1 for code-level changes and unit tests. No production/safety claim.
- Что не проверено: synthetic temporal recall after `causal_runtime`; event-level recall; ROS2 runtime replay with any new candidate; C++ parity/export for rejected candidates.
- Известные FP/FN или safety-риски: single-frame synthetic placements train the component classifier but are not a fair synthetic recall test after causal temporal; `UNKNOWN` remains `UNKNOWN != CLEAR` and is counted as FP only in metrics.
- Следующий минимальный тест: create a separate synthetic temporal dataset with stable `event_id` and 10-frame events, then evaluate event-level recall after causal warm-up.
- Residual risk: no100 single-frame synthetic may bias component classification toward isolated components; it should not be used as final acceptance evidence for `model + causal_runtime`.
