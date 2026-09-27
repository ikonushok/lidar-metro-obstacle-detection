# Synthetic seeded splits dataset run

Дата: 2026-09-24. Этап 5, режим `patch` / `validation`.

## Цель

Построить первый `synthetic_obstacles_v1_seeded_splits` dataset layer без обучения моделей: frozen split, manifest, sparse point-label sidecars, component rows и baseline `model_v1` matching для 12 synthetic scenarios, 3 дистанций и 3 зон.

## Scope и non-goals

- Allowed: новый dataset builder, новый уникальный артефакт `artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1_seeded_splits_20260924/`, этот отчёт.
- Non-goals: не обучать кандидатов, не менять runtime default model, не менять C++/ROS2 pipeline, не заявлять real-world recall.
- Источник кадров этого запуска: только `doubleT_obstacle:0:2`, то есть 2 compact usable XYZ frames до реального positive interval.

## Что добавлено

- `scripts/build_synthetic_recall_dataset.py`
  - строит placement matrix `scenario × distance × zone`;
  - сдвигает synthetic geometry в assumed `lidar_livox` source coordinates;
  - фиксирует split до обучения;
  - пишет `manifest.jsonl`, `split_manifest.json`, `generation_summary.json`;
  - пишет sparse point-label sidecars с `default=none` и явными synthetic point indices;
  - пишет `component_rows/*.json`, `component_rows.json`, `baseline_model_v1/*.json`;
  - запускает baseline `curve_pipeline_stream_cli 2.0 --compare-noise-filters`;
  - отказывается писать в непустой output.

## Команды

Syntax check:

```powershell
& 'C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile scripts\build_synthetic_recall_dataset.py scripts\smoke_synthetic_recall_real_frames.py scripts\smoke_synthetic_recall_dataset.py src\synthetic_obstacle_generator.py
```

Результат: PASS.

Dataset layer:

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" -w /workspace -e PYTHONPATH=/workspace/src:/workspace/scripts lidar-mosmetro3d:synthetic-obstacles python3 scripts/build_synthetic_recall_dataset.py --output artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1_seeded_splits_20260924 --source-window doubleT_obstacle:0:2
```

Результат: PASS.

Проверки артефакта:

- `generation_summary.json` прочитан.
- `split_manifest.json` прочитан.
- `manifest.jsonl` содержит 216 строк.
- sparse sidecar format проверен на `point_labels/doubleT_obstacle_frame_0000_low_box_d010_center.json`.

## Итоговые числа

```json
{
  "manifest_rows": 216,
  "placements_per_frame": 108,
  "component_rows": 18174,
  "split_counts": {
    "train": 40,
    "calibration": 48,
    "synthetic_held_out": 128
  },
  "baseline_model_v1_component_metrics": {
    "positive_components": 246,
    "model_tp_components": 56,
    "model_fn_components": 190,
    "model_fp_components": 0,
    "unknown_rows": 0
  }
}
```

Visibility failures: 18 rows. Все относятся к thin/far observed-ray limitations:

- `crowbar` at 30m and 60m: 12 rows;
- `shovel` at 60m: 6 rows.

## Scenario slices

`model_v1` baseline на этом synthetic layer:

| scenario | TP | FN | positive components |
|---|---:|---:|---:|
| low_box | 0 | 18 | 18 |
| cable | 0 | 16 | 16 |
| pipe_across_track | 0 | 16 | 16 |
| shovel | 0 | 12 | 12 |
| jacket_bundle | 0 | 16 | 16 |
| crowbar | 0 | 6 | 6 |
| dog_lying | 2 | 21 | 23 |
| dog_standing | 12 | 12 | 24 |
| standing_person | 10 | 11 | 21 |
| lying_person | 12 | 4 | 16 |
| suitcase | 10 | 4 | 14 |
| maintenance_trolley | 10 | 54 | 64 |

Главный вывод: текущий `model_v1` не является достаточным baseline для low/thin synthetic recall. Обучение новых кандидатов должно оптимизироваться не только по real hard-negative FP, но и по synthetic held-out FN на `low_box`, `cable`, `pipe_across_track`, `shovel`, `jacket_bundle`, `crowbar`.

## Validation

Уровень: L1 для dataset-layer формата и baseline component matching.

Что доказано:

- builder создаёт frozen split и полный набор sidecars/component rows;
- baseline `model_v1` можно посчитать на synthetic placements без изменения runtime;
- `UNKNOWN_FP` в этом запуске равен 0, `model_v1_FP` равен 0;
- synthetic FN baseline явно выявлены.

Что не доказано:

- real-world recall;
- causal temporal metric;
- перенос на другие source runs;
- качество candidate training;
- parity/export в C++ для новых моделей.

## Blockers перед обучением кандидатов

- Использован только один source window: `doubleT_obstacle:0:2`. Перед финальным выбором модели нужен wider build по нескольким real-negative windows и `doubleT_obstacle 13-64` regression.
- Causal temporal пока не считается; текущие числа component-level.
- Sidecar sparse object-level; part-level labels ещё не сохранены.
- Visibility failures для тонких дальних объектов надо оставить в denominator отчёта отдельно и не превращать в positive training samples.
- Hard-negative evaluator ещё не читает этот synthetic dataset напрямую; следующий кодовый шаг — adapter from `component_rows.json` to candidate training rows.

## Следующий минимальный шаг

Расширить dataset build без обучения:

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" -w /workspace -e PYTHONPATH=/workspace/src:/workspace/scripts lidar-mosmetro3d:synthetic-obstacles python3 scripts/build_synthetic_recall_dataset.py --output artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1_seeded_splits_multi_source_20260924 --source-window doubleT_obstacle:0:2 --source-window doubleT_obstacle:13:2 --source-window roundT_doubleT:0:2 --source-window doubleT_platform:0:2
```

После этого — интегрировать `component_rows.json` в training/evaluator и только затем запускать candidates:

1. `model_v1 + temporal`;
2. `decision_tree + temporal`;
3. `random_forest + temporal`;
4. `gradient_boosting + temporal`;
5. `lightgbm + temporal`, если зависимость доступна;
6. `ensemble_v1 + temporal`.
