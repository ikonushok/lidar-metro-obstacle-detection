# Synthetic recall smoke и уточнение плана обучения

Дата: 2026-09-24. Этап 5, режим `patch` / `validation`.

## Цель

Уточнить план обучения baseline/кандидатов с учётом текущего hard-negative evaluator и проверить минимальный synthetic dataset layer: manifest, point-label sidecar и component-level TP/FN/FP сначала на tiny fixtures, затем на 1-2 реальных source frames и 2-3 scenarios. Full synthetic build/training не запускался.

## Scope и non-goals

- Allowed: `docs/stages/stage_5/stage_5_synthetic_model_training_plan.md`, новый smoke-инструмент, этот отчёт, новый уникальный smoke-артефакт.
- Avoid: runtime default model, C++/ROS2 model replacement, geometry/envelope/frame/units, full replay/training, `UNKNOWN` upstream audit.
- Synthetic smoke не является real-world recall evidence.

## Что изменено в плане

- Зафиксировано, что текущий hard-negative evaluator уже поддерживает batch-predict, progress logging, checkpoints, saved sklearn/LightGBM models, threshold calibration и hard-negative mining.
- Добавлено правило: `UNKNOWN_FP` считать отдельно от `model_temporal_FP`; `UNKNOWN` не майнится как hard negative для component classifier.
- Full synthetic pipeline должен сохранять `component_rows/`, `checkpoints/`, `trained_models/`.
- Full run должен использовать saved component rows, чтобы не повторять synthetic generation при threshold/model experiments.
- Acceptance теперь требует не ухудшать `UNKNOWN_FP`, но не использовать его как доказательство качества модели.
- Prompt следующей сессии обновлён: сначала smoke dataset layer и component TP/FN/FP, затем full dataset build только по отдельному подтверждению.

## Что добавлено в код

- `scripts/smoke_synthetic_recall_dataset.py`: offline smoke dataset builder.
  - Строит tiny source-frame fixtures по центрам частей выбранных scenarios.
  - Запускает `raycast_scene`.
  - Сохраняет `manifest.jsonl`, `ground_truth/*.json`, `point_labels/*.json`.
  - Считает connected components и synthetic component matching.
  - Публикует oracle component metrics только для проверки формата/matching.
- `scripts/smoke_synthetic_recall_real_frames.py`: real-frame smoke dataset builder.
  - Читает 1-2 кадра из `ArchiveBagFrames`, без ROS replay.
  - Запускает `raycast_scene` на compact usable XYZ из архива.
  - Сохраняет `manifest.jsonl`, `ground_truth/*.json`, `point_labels/*.json`, `component_rows/*.json`, `baseline_model_v1/*.json`.
  - Прогоняет `curve_pipeline_stream_cli 2.0 --compare-noise-filters` и считает baseline `model_v1` TP/FN/FP по synthetic labels.
  - Отказывает писать в непустой output-каталог.

Runtime, C++ model и ROS2 node не менялись.

## Smoke-команды

Синтаксис:

```powershell
& 'C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile scripts\smoke_synthetic_recall_dataset.py scripts\evaluate_noise_model_candidates.py src\synthetic_obstacle_generator.py
```

Результат: PASS.

Попытка запустить smoke тем же bundled Python завершилась `ModuleNotFoundError: No module named 'yaml'`. Попытка через `.venv` не стартовала, потому что launcher указывает на отсутствующий `C:\Users\Ilya\AppData\Local\Programs\Python\Python312\python.exe`. `py.exe` также не нашёл установленный Python. Поэтому smoke выполнен в уже существующем Docker image, без replay/training:

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" -w /workspace -e PYTHONPATH=/workspace/src:/workspace/scripts lidar-mosmetro3d:synthetic-obstacles python3 scripts/smoke_synthetic_recall_dataset.py --output artefacts/stage_5/synthetic_obstacles/synthetic_recall_smoke_20260924 --source-frame-count 2 --scenario low_box --scenario cable --scenario standing_person
```

Результат: PASS.

```json
{
  "manifest_rows": 6,
  "components": 22,
  "oracle_component_metrics": {
    "tp_components": 16,
    "fn_components": 0,
    "fp_components": 0,
    "tn_components": 6
  },
  "visibility_failures": []
}
```

Артефакт: `artefacts/stage_5/synthetic_obstacles/synthetic_recall_smoke_20260924/`.

Проверено, что первые manifest rows содержат `point_labels`, `ground_truth`, `synthetic_returns`, `positive_component_count`, `source_frame=lidar_livox` и `target_from_source=lidar_livox <- lidar_livox`.

Real-frame smoke baseline:

```powershell
& 'C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile scripts\smoke_synthetic_recall_real_frames.py scripts\smoke_synthetic_recall_dataset.py scripts\evaluate_noise_model_candidates.py src\synthetic_obstacle_generator.py
```

Результат: PASS.

Первый запуск Docker из sandbox без эскалации не получил доступ к Docker engine/config. Повторный запуск с тем же scope выполнен:

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" -w /workspace -e PYTHONPATH=/workspace/src:/workspace/scripts lidar-mosmetro3d:synthetic-obstacles python3 scripts/smoke_synthetic_recall_real_frames.py --output artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1_smoke_real_frames_20260924 --source doubleT_obstacle --first 0 --count 2 --scenario low_box --scenario cable --scenario standing_person
```

Результат: PASS.

```json
{
  "manifest_rows": 6,
  "component_rows": 504,
  "visibility_failures": [],
  "baseline_model_v1_component_metrics": {
    "positive_components": 6,
    "model_tp_components": 2,
    "model_fn_components": 4,
    "model_fp_components": 0,
    "unknown_rows": 0
  }
}
```

Артефакт: `artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1_smoke_real_frames_20260924/`.

По manifest:

- `low_box`: 2/2 positive components стали `model_v1_FN`, synthetic returns 1836/1850.
- `cable`: 2/2 positive components стали `model_v1_FN`, synthetic returns 166/170.
- `standing_person`: 2/2 positive components стали `model_v1_TP`, synthetic returns 782/788.
- `UNKNOWN` строк нет, `model_v1_FP=0`; это маленький smoke, не итоговая метрика.

## Validation

Уровень: L1 для synthetic smoke format/matching и baseline component matching на 1-2 реальных кадрах. Это не full replay, не обучение, не runtime-check ROS2 и не доказательство recall на реальных препятствиях.

Validation reviewer pass текущим агентом: `PASS_WITH_RISKS`. Evidence поддерживает только утверждение, что минимальный manifest/label/component-matching слой работает на tiny fixtures и compact real-frame smoke.

## Blockers перед full synthetic dataset build

Нет blocker по формату smoke: manifest, point-label sidecars, component rows и baseline component metrics создаются.

Новый важный риск до обучения: baseline `model_v1` в real-frame smoke пропускает low/thin synthetic positives (`low_box`, `cable`). Поэтому обучать только на текущем `doubleT_obstacle` или менять порог hard-negative модели без synthetic positives нельзя: это может закрепить FN на низких/тонких объектах.

Остаются обязательные шаги перед full build:

- выбрать реальные source windows/frames для full generation, включая clean negative windows и `doubleT_obstacle` regression;
- расширить point-label sidecar детализацией до part/visibility state, если нужен part-level overlap;
- определить split manifest до обучения;
- прогнать `model_v1` baseline на synthetic dataset;
- интегрировать synthetic component rows с hard-negative evaluator;
- сохранить thresholds, checkpoints и trained models;
- считать `UNKNOWN_FP` и `model_temporal_FP` отдельно.

## Следующий минимальный full run

Не training всех моделей. Следующий минимальный full шаг:

1. Сформировать `synthetic_obstacles_v1_seeded_splits` без обучения: несколько real source windows, все 12 scenarios, distance/zone placements, frozen `train/calibration/synthetic_held_out/real_regression`.
2. Сохранить `manifest.jsonl`, `split_manifest.json`, `point_labels/`, `component_rows/`, `baseline_model_v1/`.
3. Прогнать baseline `model_v1 + causal temporal` как baseline evidence, отдельно считая `UNKNOWN_FP` и `model_temporal_FP`.
4. Проверить срезы low/thin/near/boundary; `low_box` и `cable` из smoke должны быть явными acceptance probes.
5. После этого отдельно запускать обучение кандидатов `decision_tree`, `random_forest`, `gradient_boosting`, optional `lightgbm`, `ensemble_v1`.

## Residual risk

Текущий лучший real-source hard-negative результат `TP=52 FN=0 FP=193` не доказывает recall новых препятствий: это один реальный объект и остаточные `193` относятся к `UNKNOWN`. Synthetic pipeline должен проверять low/thin/near FN, а не подменять upstream `UNKNOWN` audit.
