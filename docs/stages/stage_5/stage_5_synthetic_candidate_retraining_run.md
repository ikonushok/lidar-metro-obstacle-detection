# Synthetic candidate retraining run

Дата: 2026-09-24. Этап 5, режим `patch` / `validation`.

## Цель

После перехода runtime baseline с `legacy_tree_v1/model_v1` на `candidate_baseline_v2` проверить следующий шаг: переобучить модели из списка на synthetic component rows и сравнить их против фиксированного `candidate_baseline_v2`.

## Scope и non-goals

- Allowed: новый offline synthetic evaluator, новый output-каталог в `artefacts/stage_5/synthetic_obstacles/`, этот отчёт.
- Non-goals: не менять runtime default, не менять C++/ROS2, не выбирать финальную модель, не заявлять real-world recall.
- Synthetic results остаются development evidence: они проверяют low/thin probes, но не заменяют независимый real positive test.

## Входы

- Synthetic component rows: `artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1_seeded_splits_20260924/component_rows.json`.
- Fixed baseline: `models/noise_classifier_candidate_baseline_v2.json`.
- Split protocol:
  - train: synthetic `train`;
  - threshold calibration: synthetic `calibration`;
  - evaluation: `synthetic_held_out`.

## Что добавлено

- `scripts/evaluate_synthetic_noise_model_candidates.py`
  - читает `component_rows.json`;
  - строит training rows по `synthetic_point_count > 0`;
  - тренирует модели из `evaluate_noise_model_candidates.py`;
  - добавляет фиксированный `candidate_baseline_v2`;
  - калибрует thresholds на `calibration`;
  - оценивает `synthetic_held_out`;
  - сохраняет trained models и portable `random_forest_lite`.

## Команды

Syntax check:

```powershell
& 'C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile scripts\evaluate_synthetic_noise_model_candidates.py scripts\evaluate_noise_model_candidates.py scripts\build_synthetic_recall_dataset.py
```

Результат: PASS.

Synthetic candidate run:

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" -w /workspace -e PYTHONPATH=/workspace/src:/workspace/scripts lidar-mosmetro3d:noise-candidates-ml python3 scripts/evaluate_synthetic_noise_model_candidates.py --component-rows artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1_seeded_splits_20260924/component_rows.json --candidate-baseline-v2 models/noise_classifier_candidate_baseline_v2.json --output artefacts/stage_5/synthetic_obstacles/synthetic_noise_model_candidates_v1_20260924
```

Результат: PASS.

Output: `artefacts/stage_5/synthetic_obstacles/synthetic_noise_model_candidates_v1_20260924/synthetic_noise_model_candidates.json`.

## Dataset summary

```json
{
  "training_components": 3382,
  "training_class_counts": {"true": 62, "false": 3320},
  "calibration_frames": 48,
  "synthetic_held_out_frames": 128
}
```

## Synthetic held-out ranking

Основная таблица ниже — `model + temporal`, где temporal является diagnostic adjacent confirmation внутри placement event key.

| Candidate | Threshold | Temporal TP | Temporal FN | Temporal FP | Raw FN | Raw FP |
|---|---:|---:|---:|---:|---:|---:|
| `tree_depth3 + temporal` | 0.400966 | 77 | 5 | 46 | 5 | 46 |
| `decision_tree + temporal` | 0.925896 | 67 | 15 | 46 | 15 | 46 |
| `tree_depth5_min10 + temporal` | 0.967742 | 63 | 19 | 0 | 19 | 25 |
| `lightgbm + temporal` | 0.967742 | 62 | 20 | 0 | 19 | 0 |
| `ensemble_v1 + temporal` | 0.741935 | 60 | 22 | 0 | 21 | 0 |
| `random_forest_lite + temporal` | 0.806452 | 40 | 42 | 0 | 40 | 0 |
| `gradient_boosting + temporal` | 0.935484 | 38 | 44 | 0 | 43 | 0 |
| `random_forest + temporal` | 0.806452 | 36 | 46 | 0 | 45 | 0 |
| `candidate_baseline_v2 + temporal` | 0.806452 | 2 | 80 | 0 | 80 | 0 |

## Low/thin slice

Low/thin scenarios: `low_box`, `cable`, `pipe_across_track`, `shovel`, `jacket_bundle`, `crowbar`.

| Candidate | Low/thin TP | Low/thin FN | Low/thin FP |
|---|---:|---:|---:|
| `tree_depth3 + temporal` | 44 | 2 | 22 |
| `decision_tree + temporal` | 40 | 6 | 22 |
| `tree_depth5_min10 + temporal` | 40 | 6 | 0 |
| `lightgbm + temporal` | 36 | 10 | 0 |
| `ensemble_v1 + temporal` | 36 | 10 | 0 |
| `random_forest_lite + temporal` | 22 | 24 | 0 |
| `gradient_boosting + temporal` | 24 | 22 | 0 |
| `random_forest + temporal` | 22 | 24 | 0 |
| `candidate_baseline_v2 + temporal` | 0 | 46 | 0 |

## Вывод

`candidate_baseline_v2` как новый real-source baseline отлично suppress-ит component FP, но почти слепой на synthetic low/thin held-out: `TP=2`, `FN=80`.

Первый synthetic retraining показывает два разных режима:

- aggressive recall: `tree_depth3` и `decision_tree` резко уменьшают FN, но дают `46` temporal FP; это пока не replacement-кандидаты;
- conservative candidates: `lightgbm`, `ensemble_v1`, `tree_depth5_min10` дают `0` temporal FP и сильно уменьшают FN относительно `candidate_baseline_v2`.

На текущем synthetic-only срезе лучший balanced candidate: `lightgbm + temporal` (`FN=20`, `FP=0`, raw `FN=19`, raw `FP=0`). Если избегать зависимости LightGBM, следующий кандидат: `ensemble_v1 + temporal` или `tree_depth5_min10 + temporal`, но оба требуют проверки real hard-negative regression.

## Validation

Уровень: L1 для offline synthetic component-row screening.

Доказано:

- adapter может обучить все модели из списка на synthetic train split;
- thresholds калибруются на calibration split;
- synthetic held-out выявляет сильный recall gap у `candidate_baseline_v2`;
- trained artifacts сохранены в `trained_models/`.

Не доказано:

- real-source FP после synthetic retraining;
- full multi-source synthetic dataset robustness;
- C++ export/parity для новых synthetic-trained моделей;
- ROS2 runtime readiness.

## Следующий минимальный шаг

Перед runtime replacement после `candidate_baseline_v2`:

1. расширить synthetic dataset до multi-source windows;
2. добавить real hard-negative regression в тот же evaluator или объединённый отчёт;
3. проверить `lightgbm`, `ensemble_v1`, `tree_depth5_min10` на real seven-source FP;
4. выбрать кандидата только если он сохраняет `candidate_baseline_v2` FP-поведение и улучшает synthetic low/thin recall;
5. затем делать export/parity/C++.
