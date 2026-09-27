# Stage 5: model_v1 + temporal vs real-FP/synthetic candidates

## Задача

- Goal: обучить новую версию компонентного классификатора на реальных ложных срабатываниях `model_v1 + temporal` из первых 10 минут `new_data` и на новой synthetic train матрице, затем честно сравнить `model_v1 + temporal` с `random_forest + temporal`, `gradient_boosting + temporal`, `lightgbm + temporal`.
- Наблюдаемая проблема или исходный claim: старые candidate/rejected результаты не являются новым экспериментом; baseline должен быть `model_v1 + temporal`, temporal policy не переобучается и не меняется.
- Non-goals: не менять ROS2 temporal policy, runtime thresholds, envelope, safety contracts, C++/ROS2 integration; не использовать test для hard-negative mining, threshold или hyperparameter selection; не переиспользовать старый rejected `model_v2` и старую 108-placement матрицу как результат.
- Source of truth: запрос пользователя 2026-09-24, `docs/README_synthetic_obstacles.md`, `docs/README_noise_classifier.md`, фактический код/артефакты.
- Пункт/раздел ТЗ и обязательный результат: development quality comparison, not production safety claim.
- Этап docs/README_work_plan.md: stage 5 experiments/metrics.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: локальный Docker image `lidar-mosmetro3d:noise-candidates-ml` или более свежий compatible image.
- Входные данные и единицы: source-frame XYZ metres; current CORE components from current C++ stream.
- Конкретный bag/версия/интервал, топик и объём выборки: `new_data` `[0,600)` train, expected 6000 frames and 232 baseline FP; `new_data` `[600,end)` plus other real datasets for test; `doubleT_obstacle` frames 13-64 positive regression.
- Факты из docs/README_dataset_audit.md, подтверждения на текущем входе и непроверенные предположения: exact trainable CORE component count among 232 FP must be measured in this task.
- Рабочие frames и направление transforms: current synthetic config `lidar_livox <- lidar_livox`; no extrapolated 100 m geometry claim until feasibility passes.
- Режим baseline/расширений; необходимые TF/движение/карта/габарит и поведение при их отсутствии: compare only `model + same temporal`; UNKNOWN stays runtime UNKNOWN and is counted as FP only in metric tables.
- Временная база событий и способ измерения вычислительной задержки: bag offsets for split; process monotonic clocks for computation timing.
- Allowed files: `config/stage_5_real_synthetic_noise_experiment.yaml`, `scripts/build_synthetic_recall_dataset.py`, new stage-5 experiment scripts/reports/artifacts, focused tests, `docs/README_synthetic_obstacles.md`.
- Files to avoid: ROS2 temporal policy/runtime, envelope geometry, C++ thresholds, old rejected model artifacts except as historical references.
- Защищённые контракты: `UNKNOWN != CLEAR`; test never used for training/tuning; temporal unchanged; no hidden synthetic component fabrication for untrainable real FP.
- Deliverables и статус каждого: versioned config — implemented; split manifest support — implemented; 100 m feasibility — failed gate; 1152 train manifest — blocked by feasibility; baseline metrics for `new_data [0,600)` — implemented; final model — not trained; rejected candidate — not created because full training was not permitted.
- Путь отчёта этапа или категории: `docs/stages/stage_5/stage_5_real_fp_synthetic_model_v3.md`.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer` и почему: нет для текущего config/generator-only шага; потребуется, если менять geometry/envelope.
- Нужен ли отдельный этап `validation_reviewer`; порядок и кто выполняет проходы: да перед claim о снижении FP/сохранении 52/52.
- Validation target: L1 for generator/config/tests; L3/L4 only after full replay across requested datasets.
- Validation method: focused unit tests; feasibility generation at 100 m; full synthetic train/held-out generation; real train/test replay; grouped temporal CV on development train only.
- Acceptance criteria: lower real FP than `model_v1 + temporal`; `doubleT_obstacle` remains 52/52; low/thin synthetic not critically worse; no test leakage; rejected candidate saved if fail.
- Stop conditions: 100 m feasibility cannot provide 288 valid examples; source frame/axis mismatch; trainable CORE count among 232 FP is zero or unmeasured; any need to change temporal/envelope/runtime thresholds.

## Отчёт о завершении

- Что изменено: добавлен versioned config `stage5_real_fp_synthetic_v1_20260924`; synthetic builder получил явные split policies `all_train`/`all_synthetic_held_out`; offline temporal evaluator приведён к текущему runtime rule: 2 последовательных alarm, reset на `UNKNOWN`; сохранены compact feasibility/baseline artifacts.
- Evidence inspected: `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `agents/validation_reviewer.md`, current synthetic generator/evaluators/docs, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp` temporal contract, generated artifacts under `artefacts/stage_5/real_fp_synthetic_v1_20260924/`.
- Commands run:
  - `docker run --rm -v ${PWD}:/app -w /app lidar-mosmetro3d:noise-candidates-ml python3 -m unittest tests.test_build_synthetic_recall_dataset tests.test_synthetic_obstacle_generator` — PASS, 15 tests.
  - `docker run --rm -v ${PWD}:/workspace -w /workspace lidar-mosmetro3d:noise-candidates-ml python3 scripts/build_synthetic_recall_dataset.py ... --source-window roundT_doubleT:0:8 --distance-m 100 ...` — BLOCKED: `SOURCE_FRAME_MISMATCH:hesai_lidar!=lidar_livox`.
  - source-frame sample audit via `ArchiveBagFrames` — only `doubleT_obstacle` has `lidar_livox`; all other listed real archives sampled as `hesai_lidar`.
  - `docker run --rm ... scripts/build_synthetic_recall_dataset.py --source-window doubleT_obstacle:0:8 --distance-m 100 --zone center --zone left_boundary --zone right_boundary --split-policy all_train` — completed 288 placements.
  - `docker run --rm ... scripts/evaluate_noise_model_candidates.py --source new_data --train-source doubleT_obstacle --duration-seconds 600` before evaluator temporal fix — diagnostic only; old adjacent temporal gave `model_v1 + temporal` 216 FP by user rule.
  - `docker run --rm ... python3 -m unittest tests.test_evaluate_noise_classifier tests.test_build_synthetic_recall_dataset tests.test_synthetic_obstacle_generator` — PASS, 20 tests.
  - `docker run --rm ... scripts/evaluate_noise_model_candidates.py --source new_data --train-source doubleT_obstacle --duration-seconds 600` after causal temporal fix — baseline artifact saved.
  - `docker run --rm ... scripts/summarize_stage5_real_synthetic_gate.py ...` — wrote `gate_summary.json`.
- Baseline result on current code: `new_data [0,600)` produced 6000 frames; `model_v1 + current causal temporal` had `148` component-FP frames and `18` `UNKNOWN` frames, so user-rule FP is `166`, not the supplied expectation `232`. Trainable FP frames with usable CORE components: `148`; trainable FP components after temporal: `135`. The mismatch is recorded as evidence conflict, not hidden.
- 100 m feasibility result: 288 placements generated, but only `2/288` valid CORE-positive examples (`cable`: 1, `pipe_across_track`: 1). `15` placements had zero synthetic returns. Most classes had synthetic returns but no component in the classifier area, so they are not valid positive train examples under the requested rule.
- Validation level achieved: L1 for config/generator/evaluator changes and feasibility/baseline replay artifacts. No claim of model improvement.
- Что не проверено: no full 1152 train generation, no grouped CV, no final training, no real test evaluation, no `doubleT_obstacle` 52/52 check for a new model, no synthetic held-out result.
- Известные FP/FN или safety-риски: `UNKNOWN` counted as FP only in metrics; runtime `UNKNOWN != CLEAR` unchanged. Synthetic source-frame coverage is insufficient: using `hesai_lidar` backgrounds would require a verified transform/config, not a rename.
- Следующий минимальный тест: decide whether to create a verified `hesai_lidar <- hesai_lidar` synthetic config/geometry path or reduce the 100 m requirement; then rerun 100 m feasibility before any full train.
- Residual risk: old evaluator outputs before the temporal fix are present as local ignored artifacts but are not used as acceptance evidence; committed baseline artifact is the causal-temporal rerun.

## Продолжение 2026-09-25: fresh rail-axis fix и temporal modes

- Текущий `HEAD`: `2332b7a docs: record noise classifier v2 unknown reduction`; shared-station fix для `AMBIGUOUS_LOCAL_CONTINUITY_PATH` присутствует в `src/cpp/auto_rails_core.cpp`.
- Собран fresh Docker image из текущего кода: `lidar-mosmetro3d:stage5-current-2332b7a`, затем после evaluator update `lidar-mosmetro3d:stage5-temporal-modes`.
- Старые Docker images/component rows не использовались для новых выводов; seven-source replay заново декодировал bag archives через свежий `/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli`.
- В evaluator добавлен явный `--temporal-mode`:
  - `causal_runtime`: current alarm + previous consecutive alarm, reset on `UNKNOWN`/source boundary;
  - `legacy_adjacent`: historical offline diagnostic rule, current alarm + previous or next adjacent alarm in same source.
- Fresh `causal_runtime` artifact: `artefacts/stage_5/noise_model_candidate_current_2332b7a_all_sources/compact_summary.json`.
  - `UNKNOWN_FP=41`, rail-axis fix confirmed;
  - thresholds shifted low to preserve `TP=52/FN=0`;
  - best checked ML candidate `random_forest_lite`: `model_temporal_FP=1574`, `FP_total=1615`;
  - conclusion: this mode is not the v2 table protocol and must not be mixed with it.
- Fresh `legacy_adjacent` artifact: `artefacts/stage_5/noise_model_candidate_current_2332b7a_legacy_adjacent_all_sources/compact_summary.json`.
  - `random_forest_lite + temporal`: `threshold=0.838710`, `UNKNOWN_FP=41`, `model_temporal_FP=0`, `FP_total=41`, `TP/FN=52/0`;
  - `random_forest + temporal`: `threshold=0.774194`, `UNKNOWN_FP=41`, `model_temporal_FP=0`, `FP_total=41`, `TP/FN=52/0`;
  - `ensemble_v1 + temporal`: `threshold=0.903226`, `UNKNOWN_FP=41`, `model_temporal_FP=0`, `FP_total=41`, `TP/FN=52/0`;
  - this reproduces the v2 expectation on fresh C++ output.
- Validation level: L4 for development seven-source replay of the rail-axis upstream fix under explicit `legacy_adjacent`; L1/L3 diagnostic only for `causal_runtime` because thresholds/protocol are not yet accepted for candidate selection.
- Decision before synthetic: synthetic training/evaluation must declare temporal mode explicitly. To reproduce v2 acceptance numbers, use `legacy_adjacent`; to evaluate runtime-causal behavior, use `causal_runtime` and recalibrate separately rather than comparing to v2.
