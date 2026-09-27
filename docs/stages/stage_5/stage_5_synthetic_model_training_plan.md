# Обучение моделей на синтетике — финальный план

Дата: 2026-09-24. Этап 5, режим `plan` / documentation. Этот документ фиксирует протокол, по которому следующая сессия должна начать подготовку данных и сравнение моделей после завершения текущих параллельных процессов.

Уточнение: текущий hard-negative evaluator уже показал, что лучшие offline-кандидаты сохраняют `TP=52`, `FN=0` на единственном реальном positive interval и снижают component FP до нуля; остаточные `193` FP — это `UNKNOWN`, а не `model_temporal_FP`. Поэтому synthetic этап должен прежде всего проверять recall/FN на новых synthetic obstacles и вести `UNKNOWN_FP` отдельной upstream-колонкой.

## Задача

- Goal: подготовить воспроизводимое обучение и сравнение нескольких моделей фильтра `CORE`-компонентов на синтетических препятствиях и реальных отрицательных проездах.
- Наблюдаемая проблема или исходный claim: `model_v1` обучена только на `doubleT_obstacle`; независимых реальных positive-примеров нет. Единственный практический источник новых positive-примеров сейчас — development-only синтетика.
- Non-goals: не менять текущий runtime default `model_v1`, C++/ROS2 pipeline, envelope, frame/оси/единицы, safety/CLEAR contract, пороги габарита или правила `UNKNOWN`; не заявлять real-world recall по синтетике.
- Source of truth: `docs/README_synthetic_obstacles.md`, `docs/README_noise_classifier.md`, `docs/README_work_plan.md`, фактический генератор `src/synthetic_obstacle_generator.py`, текущие real-source eval артефакты.
- Этап `docs/README_work_plan.md`: stage 5 — генератор, фильтр ложных срабатываний, обучение на синтетике и сравнение моделей.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактический первый шаг следующей сессии должен быть low-impact до явного запуска тяжёлых replay.
- Входные данные и единицы: реальные `PointCloud2`/XYZ в `m_ASSUMED`; synthetic config только `SYNTHETIC_DEVELOPMENT_ONLY`, identity `lidar_livox <- lidar_livox`.
- Allowed files: новые dataset/training/evaluator scripts, `docs/README_synthetic_obstacles.md`, этот план, новые артефакты в уникальном каталоге `artefacts/stage_5/synthetic_obstacles/<dataset_version>/`.
- Files to avoid: текущие runtime defaults, C++ model integration, общие каталоги существующих артефактов без versioned подкаталога, исходные bag.
- Защищённые контракты: `UNKNOWN` не `CLEAR`; synthetic не safety evidence; real и synthetic метрики раздельны; held-out не используется для подбора; `doubleT_obstacle 13-64` только regression.
- Reviewer: перед заменой модели потребуется safety/validation pass; для подготовки датасета достаточно validation pass по evidence.
- Validation target: L0/L1 для подготовки протокола; L3/L4 возможен только после воспроизводимого dataset build, frozen split, full candidate evaluation и parity/export проверок.
- Stop conditions: не запускать тяжёлые Docker/replay/training, если активны параллельные процессы или нет уникального output-каталога; не выбирать модель без frozen split и held-out результата.

## Уточнение по текущему evaluator

`scripts/evaluate_noise_model_candidates.py` уже закрывает real-source hard-negative часть протокола:

- batch-predict для sklearn/LightGBM моделей;
- progress logging на train/eval/calibration;
- checkpoint JSON после обучения и после каждой модели;
- сохранение обученных sklearn/LightGBM моделей в `trained_models/*.pkl`;
- hard-negative mining через `--training-mode hard_negative` и `--hard-negative-source`;
- threshold calibration через `--calibrate-thresholds` и отдельные `--calibration-source`;
- fixed baseline: `model_v1` остаётся threshold `0.5`, если явно не задан `--calibrate-baseline`;
- сравнение `model + temporal`, overlap против `model_v1`, и раздельный смысл `UNKNOWN` как upstream/status failure.

Для synthetic pipeline это означает:

1. Не майнить `UNKNOWN` как обучающие negative-компоненты. `UNKNOWN_FP` должен идти отдельной колонкой и отдельным upstream audit, не в component-classifier loss.
2. Использовать hard-negative evaluator для real-negative части обучения/калибровки, но добавить synthetic-positive rows из point-label sidecars.
3. Считать итоговые FP минимум двумя числами: `UNKNOWN_FP` и `model_temporal_FP`. Текущий лучший real-source результат `FP total=193` означает `UNKNOWN_FP=193`, `model_temporal_FP=0`; он не доказывает recall на новых препятствиях.
4. Threshold calibration разрешена только на `calibration`, а не на `synthetic_held_out`.
5. Saved models/checkpoints становятся обязательными артефактами full synthetic run, чтобы можно было повторить export/parity без переобучения.

## Финальная схема работ

### 1. Зафиксировать synthetic dataset v1

Сначала создаётся не модель, а воспроизводимый набор:

```text
artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1/
  manifest.jsonl
  generation_summary.json
  split_manifest.json
  ground_truth/
  point_labels/
  component_rows/
  baseline_model_v1/
  candidates/
  checkpoints/
  trained_models/
```

Каждая строка manifest должна содержать source identity, frame index/timestamp, `scenario_id`, object/category/pose, placement, seed, requested/actual zone, `synthetic_returns`, nearest distance, split и generator/config hashes.

Обязательное новое поле данных: point-level sidecar labels по исходному порядку точек. Минимум: для каждого source point index указать `object_id` или `none`, `part_id` при наличии и synthetic visibility/dropout state. Без point labels нельзя честно сопоставить `CORE`-компонент с synthetic объектом.

Перед full build нужен smoke dataset layer: 1-2 source frames, 2-3 scenarios, manifest, point-label sidecar и component-level TP/FN/FP. Этот smoke не заменяет реальный replay и не создаёт training data; он проверяет формат и matching.

Текущий статус smoke на 2026-09-24:

- tiny fixture smoke: PASS, `manifest_rows=6`, `oracle_component_metrics TP=16 FN=0 FP=0 TN=6`;
- real-frame smoke: PASS на `doubleT_obstacle` frames `0-1`, scenarios `low_box`, `cable`, `standing_person`, `manifest_rows=6`, `component_rows=504`, `visibility_failures=[]`;
- baseline `model_v1` на real-frame smoke: `positive_components=6`, `model_tp_components=2`, `model_fn_components=4`, `model_fp_components=0`, `unknown_rows=0`;
- observed pattern: `standing_person` ловится 2/2, `low_box` и `cable` уходят в FN 4/4.

Первый seeded split layer тоже построен на 2026-09-24, см. `docs/stages/stage_5/stage_5_synthetic_seeded_splits_run.md`:

- source window: `doubleT_obstacle:0:2`;
- placement matrix: `12 scenarios × 3 distances × 3 zones × 2 frames = 216 rows`;
- split counts: `train=40`, `calibration=48`, `synthetic_held_out=128`;
- baseline `model_v1`: `positive_components=246`, `model_tp_components=56`, `model_fn_components=190`, `model_fp_components=0`, `unknown_rows=0`;
- visibility failures: 18 rows, only thin/far `crowbar`/`shovel` placements.

Вывод для обучения: synthetic positives нужны не как косметическое расширение, а как acceptance probe для low/thin FN. Нельзя выбирать новую модель только по снижению real hard-negative FP или `UNKNOWN_FP`: такой критерий не защищает низкие/тонкие препятствия.

### 2. Матрица placements

Первая версия набора:

```text
12 scenario_id
× 3 расстояния: 10 / 30 / 60 м
× 3 положения: центр / левая граница / правая граница
= 108 placements
```

Дополнительно для низких и тонких объектов (`low_box`, `crowbar`, `shovel`, `jacket_bundle`, `pipe_across_track`, `cable`) добавить 5 / 20 / 40 м и partial/warning-zone placements.

Если `synthetic_returns == 0`, пример сохраняется как visibility failure, но не входит в positive training/eval denominator.

### 3. Split до обучения

Split фиксируется до обучения:

- `train`: обучение кандидатов.
- `calibration`: выбор гиперпараметров/порогов.
- `synthetic_held_out`: итоговая проверка synthetic generalization.
- `real_regression`: `doubleT_obstacle 13-64` и реальные условно отрицательные источники.
- `independent_real_positive`: только если появится новый реальный positive bag.

Запрещено разделять производные одного placement/seed/source-window между train и held-out. Желательно удерживать в held-out целые object-family или distance/zone buckets, чтобы проверять перенос, а не соседние кадры.

### 4. Component matching

Обучение и оценка идут на `CORE`-компонентах, а не на кадрах:

- Positive component: компонент содержит synthetic labels объекта по заранее заданному критерию.
- Negative component: компонент без synthetic overlap, если он не помечен как ignored/unknown.
- FN: synthetic объект наблюдаем (`synthetic_returns > 0`), но нет сопоставленного reportable компонента после `model + temporal`.
- FP: reportable компонент/событие не сопоставлено ни с одним synthetic объектом.

Matching-критерий фиксируется до первого итогового прогона. Первый разумный вариант: минимум абсолютного числа synthetic points в компоненте и/или минимум доли synthetic points объекта. Порог является частью протокола, не универсальной константой.

Full evaluator должен сохранять component rows до обучения: features, labels, split, source/scenario metadata, `synthetic_point_count`, matched object ids и ignored/visibility flags. Это позволит переиспользовать текущий batch/hard-negative evaluator без повторного synthetic generation.

### 5. Кандидаты

Сравниваются сразу несколько моделей на одном frozen dataset:

1. `model_v1 + temporal` — текущий baseline, не переобучается.
2. `decision_tree + temporal` — интерпретируемый кандидат.
3. `random_forest + temporal` — устойчивый табличный кандидат.
4. `gradient_boosting + temporal` — сильный кандидат без LightGBM.
5. `lightgbm + temporal` — только если зависимость доступна и её export/runtime приемлемы.
6. `ensemble_v1 + temporal` — только если даёт held-out выигрыш после temporal.

Все модели используют одинаковые component features на первом этапе. Более сложные признаки добавляются отдельной версией датасета/протокола.

### 6. Temporal rule

Для runtime-кандидата основная метрика считается как `model + causal temporal`, совместимая с ROS2: первый одиночный alarm не публичный сигнал, второй последовательный новый alarm подтверждает событие, `UNKNOWN` сбрасывает state.

Offline future-neighbor `2-of-3` можно сохранять только как diagnostic column. Она не является acceptance-метрикой для замены модели.

Пока synthetic smoke не моделирует последовательность событий, он проверяет только component matching. Full synthetic run должен строить event groups по placement/source/scenario и считать causal temporal latency отдельно.

### 7. Метрики и overlap-анализ

Отчёт обязан содержать:

- synthetic TP/FN/FP/TN и `UNKNOWN` с абсолютными знаменателями;
- раздельно `UNKNOWN_FP` и `model_temporal_FP`;
- real FP frames/min и FP events/min отдельно;
- `doubleT_obstacle 13-64` regression;
- задержку первого и устойчивого detection;
- срезы по category, low/thin/regular/large, distance band, zone, source run;
- p50/p95 runtime на одинаковом direct C++ path после export-кандидата;
- `fp_overlap_vs_model_v1_temporal`: common FP, candidate-only FP, baseline-only FP, Jaccard, примеры;
- `synthetic_tp_overlap_matrix`: какие placements ловят все модели, только candidate, только baseline, никто;
- `synthetic_fn_regressions_vs_model_v1`: список объектов/placements, потерянных новой моделью относительно baseline.

Overlap-анализ является acceptance gate. Модель с тем же total FP может быть лучше, если добавляет held-out TP без новых опасных FN; модель с меньшим FP может быть хуже, если подавляет low/thin obstacles.

### 8. Критерий замены `model_v1`

Модель можно готовить к C++ export только если одновременно:

- `doubleT_obstacle` не потерян как event regression;
- synthetic held-out улучшает low/thin/small/far или boundary cases;
- real `model_temporal_FP` не хуже `model_v1 + causal temporal` либо улучшение объяснимо overlap-анализом;
- `UNKNOWN_FP` не ухудшается и не используется как доказательство качества component classifier;
- нет новых критичных FN на low/thin/near intrusion;
- causal temporal latency приемлема и явно измерена;
- модель можно воспроизвести/export в C++ без тяжёлого runtime dependency;
- parity JSON/offline/C++ и direct/ROS2 решения проверены на одинаковом input.

Если `decision_tree` почти не хуже сложных моделей, предпочтение ему: проще объяснить, встроить и проверить. `LightGBM` и `ensemble_v1` принимаются только при явном held-out выигрыше, покрывающем стоимость зависимости/export.

## Что не делать сейчас

- Не запускать full replay/training в текущей сессии, пока активны параллельные процессы.
- Не писать в существующие каталоги `artefacts/stage_5/noise_model_eval*` или `noise_model_candidate*`; использовать новый versioned synthetic каталог.
- Не менять runtime default `model_v1`.
- Не включать synthetic результаты в README как реальный recall.
- Не смешивать synthetic recall работу с `UNKNOWN` upstream audit: `UNKNOWN` остаётся отдельной geometry/status задачей.

## Готовый промпт для новой сессии

Скопировать после завершения текущих процессов:

```text
Начни реализацию плана `docs/stages/stage_5/stage_5_synthetic_model_training_plan.md`.

Сначала проверь, что нет активных конфликтующих процессов/серверов, и работай только в новом каталоге:
`artefacts/stage_5/synthetic_obstacles/synthetic_obstacles_v1/`.

Цель следующей сессии: расширить уже построенный `synthetic_obstacles_v1_seeded_splits_20260924` до multi-source dataset layer и подготовить adapter в evaluator, но не выбирать runtime model:
1. построить новый output-каталог с несколькими source windows, включая real-negative windows и `doubleT_obstacle 13-64` regression sample;
2. сохранить manifest/point_labels/component_rows/baseline_model_v1/split_manifest;
3. добавить adapter, который читает synthetic `component_rows.json` как training/eval rows для candidate evaluator;
4. считать `UNKNOWN_FP` и `model_temporal_FP` отдельно;
5. сохранить overlap/slice metrics по low/thin/near/boundary;
6. не менять runtime default, C++ model, envelope, frame/оси/единицы.

После multi-source build и adapter дай отчёт: команды, validation level, split counts, baseline `model_v1`, blockers перед обучением кандидатов. Обучение всех кандидатов запускать только после отдельного подтверждения.
Не запускай full seven-source replay или обучение всех кандидатов без отдельного подтверждения.
```

## Отчёт о завершении этой документационной задачи

- Что изменено: создан финальный план обучения и сравнения моделей на синтетике, включая candidates, split, matching, causal temporal, hard-negative evaluator integration, раздельные `UNKNOWN_FP`/`model_temporal_FP`, overlap-анализ, acceptance gate и prompt следующей сессии.
- Evidence inspected: `docs/README_synthetic_obstacles.md`, `docs/README_noise_classifier.md`, `docs/README_work_plan.md`, `docs/stages/stage_5/stage_5_synthetic_obstacle_generation*.md`, `src/synthetic_obstacle_generator.py`, текущий candidate-eval протокол.
- Commands run: чтение документов и `git status`; runtime/replay/training не запускались.
- Validation level achieved: L0 для документационного протокола.
- Что не проверено: full dataset build, replay настоящего bag через генератор, обучение кандидатов, C++ export/parity.
- Известные FP/FN или safety-риски: synthetic не доказывает real recall; `model_v1` может подавлять низкие/малые объекты; temporal добавляет задержку.
- Следующий минимальный тест: новая сессия по prompt выше, только smoke dataset builder.
- Residual risk: параллельные изменения в рабочем дереве могут менять фактический runtime/evaluator; перед реализацией нужна свежая проверка статуса.
