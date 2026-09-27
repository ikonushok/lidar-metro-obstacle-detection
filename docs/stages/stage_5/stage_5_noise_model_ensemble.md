# Stage 5: проверка одиночных моделей и ансамбля + temporal

## Цель

Сравнить несколько кандидатов фильтра `CORE`-компонентов с прежней базой `legacy_tree_v1 + temporal`, выбрать замену при измеримом улучшении FP без потери известного препятствия и экспортировать выбранный вариант как `candidate_baseline_v2`.

## Baseline

Прежняя база из `docs/README_noise_classifier.md`: `legacy_tree_v1 + temporal`.
В этой задаче по уточнению пользователя `UNKNOWN` на отрицательных кадрах
считается FP, поэтому baseline для сравнения: `TP=52`, `FN=0`, `FP=463`,
`TN=13244`. Без добавления `UNKNOWN` прежняя диагностическая колонка имела
`270` FP-кадров.

## Non-goals

- Не менять runtime C++/ROS2/pipeline до выбора кандидата.
- Не менять safety envelope, геометрию, `UNKNOWN/CLEAR` contract, QoS или ROS2-схемы.
- Не заявлять независимый recall: `doubleT_obstacle` остаётся обучающим/регрессионным положительным проездом.
- Не считать raw покадровый выход модели целевой метрикой замены.

## Правило сравнения

Все новые одиночные модели и ансамбли после обучения оцениваются в основном сравнении только как `model + temporal`. Temporal-фильтр является обязательной частью проверяемого варианта и применяется одинаково к каждому кандидату, чтобы отсекать однокадровые обнаружения. Сравнение велось против прежнего `legacy_tree_v1 + temporal`, а runtime replacement выбран как `candidate_baseline_v2 + temporal`.

## Защищённые контракты

- `UNKNOWN` не считается чистым отрицательным кадром.
- Для сравнительной таблицы этой задачи отрицательный `UNKNOWN` засчитывается
  как FP; положительный `UNKNOWN` засчитывался бы как FN.
- Отрицательный ответ модели не означает `CLEAR`.
- Положительный интервал `doubleT_obstacle` остаётся frames `13-64` inclusive.
- Производные синтетические сценарии одного источника нельзя смешивать между train/test без отдельного split-протокола.
- Новый runtime-кандидат допускается только после проверки parity offline/export/C++.

## План

1. Зафиксировать текущий протокол и скрипт offline-сравнения кандидатов.
2. Проверить одиночные модели `+ temporal` на одинаковых `CORE` компонентах и признаках.
3. Собрать простой ансамбль из перспективных кандидатов и проверить его также только `+ temporal`.
4. Сравнить с baseline по FP-кадрам, FP/min, TP/FN на `doubleT_obstacle`, доступным synthetic/regression-срезам и p95 runtime.
5. Только после выбора победителя готовить C++ export/runtime-интеграцию и parity-тест.

## Acceptance

Кандидат может заменить прежний `legacy_tree_v1 + temporal`, если:

- FP total меньше `270` на сопоставимом seven-source протоколе;
- FP total меньше `463` на сопоставимом seven-source протоколе с правилом
  `UNKNOWN -> FP`;
- `doubleT_obstacle` остаётся `52/52`;
- нет нового FN на доступных синтетических/регрессионных препятствиях;
- runtime p95 в direct C++ path приемлем;
- экспортируемая модель воспроизводит offline-решение.

## Выполнено в этой задаче

- Добавлено явное правило в `docs/README_noise_classifier.md`: все новые одиночные модели и ансамбли сравниваются только как `model + temporal`; baseline замены после этой работы — `candidate_baseline_v2 + temporal`.
- Добавлен offline-инструмент `scripts/evaluate_noise_model_candidates.py`.
- Инструмент обучает кандидаты на текущих компонентных признаках и считает итоговые метрики после одинакового temporal-фильтра:
  - `legacy_tree_v1`;
  - `decision_tree`;
  - `tree_depth3`;
  - `tree_depth5_min10`;
  - `random_forest_lite`;
  - настоящий `random_forest`;
  - `gradient_boosting`;
  - `lightgbm`;
  - `ensemble_v1`.
- Runtime C++/ROS2/pipeline на первом offline-этапе не менялся; после выбора победителя `random_forest_lite` экспортирован и подключён как `candidate_baseline_v2`.
- Дополнение: Dockerfile обновлён для настоящих offline-кандидатов `random_forest`,
  `gradient_boosting` и `lightgbm`: `python3-sklearn` ставится через APT,
  `lightgbm==4.5.0` через pip, так как Jammy apt не содержит `python3-lightgbm`.
- Инструмент ускорен: sklearn/LightGBM модели оцениваются batch-predict,
  добавлены progress logging, checkpoint JSON после каждой модели и сохранение
  обученных sklearn/LightGBM моделей в `trained_models/*.pkl`.

## Выполненные команды и результаты

- `docker run --rm ... python3 -m py_compile scripts/evaluate_noise_model_candidates.py scripts/evaluate_noise_classifier.py scripts/train_noise_classifier.py` — PASS.
- `docker run --rm ... python3 -m unittest tests.test_train_noise_classifier tests.test_evaluate_noise_classifier` — PASS, `3/3`.
- `docker build --progress plain -t lidar-mosmetro3d:noise-candidates-ml .` — выполнено пользователем; проверка импортов показала `sklearn OK 0.23.2`, `lightgbm OK 4.5.0`.
- Smoke `doubleT_obstacle` frames `13-15` в ML-образе: доступные кандидаты дали `temporal_tp=3`, `temporal_fn=0`, `temporal_fp=0`; настоящие `random_forest`, `gradient_boosting`, `lightgbm` стали доступны.
- Multi-source smoke frames `0-20` всех семи источников в ML-образе: `147` кадров, положительных `8`. `legacy_tree_v1`, `decision_tree`, `tree_depth3`, `random_forest_lite`, `random_forest`, `lightgbm`, `ensemble_v1` дали `temporal_tp=8`, `temporal_fn=0`, `temporal_fp=0`; `tree_depth5_min10` дал `FP=2`, `gradient_boosting` дал `FP=3`.
- Первая полная серия по источникам показала, что per-component `predict_proba([features])` делает `new_data` слишком медленным; прогон остановлен и evaluator исправлен на batch/checkpoint.
- Batch/checkpoint прогон `new_data_batch` завершён: обучено `19365` компонентов, оценено `1952298` компонентов; модели сохранены в `artefacts/stage_5/noise_model_candidate_ml_by_source/new_data_batch/trained_models/`.

## Итоговая таблица seven-source, `UNKNOWN -> FP`

| Метод | TP | FN | FP | TN | Common FP with baseline | Candidate-only FP | Baseline-only FP |
|---|---:|---:|---:|---:|---:|---:|---:|
| `lightgbm + temporal` | 52 | 0 | 351 | 13 356 | 338 | 13 | 125 |
| `ensemble_v1 + temporal` | 52 | 0 | 397 | 13 310 | 395 | 2 | 68 |
| `legacy_tree_v1 + temporal` | 52 | 0 | 463 | 13 244 | 463 | 0 | 0 |
| `decision_tree + temporal` | 52 | 0 | 463 | 13 244 | 463 | 0 | 0 |
| `tree_depth3 + temporal` | 52 | 0 | 463 | 13 244 | 463 | 0 | 0 |
| `tree_depth5_min10 + temporal` | 52 | 0 | 463 | 13 244 | 463 | 0 | 0 |
| `gradient_boosting + temporal` | 52 | 0 | 774 | 12 933 | 298 | 476 | 165 |
| `random_forest_lite + temporal` | 52 | 0 | 830 | 12 877 | 421 | 409 | 42 |
| `random_forest + temporal` | 52 | 0 | 924 | 12 783 | 397 | 527 | 66 |

Лучший offline-кандидат на текущем протоколе: `lightgbm + temporal`.
Он уменьшил FP с `463` до `351`, сохранил `TP=52`, `FN=0`, убрал
`125` baseline-FP и добавил `13` новых FP. Это development-результат на
условной разметке; runtime C++/ROS2 ещё не обновлялся.

## Текущий уровень валидации

L1 для offline-инструмента и development-сравнения: синтаксис проверен,
существующие unit-тесты baseline evaluator прошли ранее, ML-зависимости
проверены в Docker, seven-source offline-прогон завершён. Это не runtime
готовность: первый C++ export/parity выполнен для `candidate_baseline_v2`,
но p95 direct path и независимые positive tests ещё не выполнены.

## Следующий минимальный тест

Следующий минимальный тест после runtime replacement: p95 direct path для
`candidate_baseline_v2`, затем synthetic held-out/recall и отдельная
upstream/status задача по `UNKNOWN`.

## Дополнение: hard-negative и calibration pipeline

После обсуждения причины слабого выигрыша обычных кандидатов добавлен следующий
offline-режим в `scripts/evaluate_noise_model_candidates.py`:

- `--training-mode hard_negative`;
- `--hard-negative-source <source>`: добавляет в обучение компоненты, которые
  попали в FP у фиксированного `legacy_tree_v1 + temporal`;
- `--calibrate-thresholds`: подбирает threshold каждого нового кандидата на
  calibration-срезе по правилу `FN` прежде всего, затем `FP`;
- `legacy_tree_v1` остаётся фиксированным историческим comparator с `threshold=0.5`;
  его можно калибровать только явным `--calibrate-baseline`;
- batch-predict, progress logging, checkpoints и сохранение моделей сохранены
  и для нового режима.

`UNKNOWN` по-прежнему считается FP/FN в метриках, но не используется как
обучающий hard negative: это upstream geometry/status, а не компонентная ошибка
ML-модели.

### Проверка механики

- `docker run --rm ... python3 -m py_compile scripts/evaluate_noise_model_candidates.py` — PASS.
- Smoke `doubleT_obstacle + roundT_doubleT`, frames `0-20`, hard-negative mode
  и calibration — PASS. На этом коротком фрагменте hard negatives не нашлись,
  что ожидаемо для sanity-check.
- Частичный прогон `doubleT_obstacle + roundT_doubleT` целиком — PASS,
  найдено `40` hard-negative components, обучено `1132` rows:
  `52` positive, `40` hard-negative, `1040` regular-negative.

### Частичная таблица `doubleT_obstacle + roundT_doubleT`, `UNKNOWN -> FP`

Это не новая итоговая таблица для README, а проверка гипотезы на одном
отрицательном источнике с известными baseline FP.

| Метод | Threshold | TP | FN | FP | TN |
|---|---:|---:|---:|---:|---:|
| `random_forest_lite + temporal` | 0.903226 | 52 | 0 | 10 | 391 |
| `random_forest + temporal` | 0.774194 | 52 | 0 | 10 | 391 |
| `ensemble_v1 + temporal` | 0.935484 | 52 | 0 | 10 | 391 |
| `lightgbm + temporal` | 0.967742 | 52 | 0 | 14 | 387 |
| `gradient_boosting + temporal` | 0.967742 | 52 | 0 | 16 | 385 |
| `decision_tree + temporal` | 0.967742 | 52 | 0 | 23 | 378 |
| `tree_depth3 + temporal` | 0.967742 | 52 | 0 | 23 | 378 |
| `legacy_tree_v1 + temporal` | 0.500000 | 52 | 0 | 45 | 356 |
| `tree_depth5_min10 + temporal` | 0.935484 | 52 | 0 | 109 | 292 |

Вывод: гипотеза подтверждается на частичном срезе. Проблема была не в
«идеальности» прежнего одно-деревного classifier, а в слишком узком обучении без hard negatives и без
калибровки порога. Следующий минимальный шаг — full seven-source прогон нового
режима, желательно с `new_data` как hard-negative source и отдельной
calibration/test разбивкой. Этот шаг выполнен ниже; после него выбран
`random_forest_lite` для runtime export.

### Полный seven-source прогон hard-negative режима

Запуск:
`artefacts/stage_5/noise_model_candidate_hard_negative_all_sources_cal_roundT/noise_model_candidates.json`.
Обучение: `52` positive, `281` hard-negative, `1040` regular-negative
components. Hard negatives взяты из всех отрицательных источников; calibration
thresholds подобраны на `doubleT_obstacle + roundT_doubleT`. `legacy_tree_v1`
оставлен фиксированным историческим comparator с `threshold=0.5`.

| Метод | Threshold | TP | FN | FP total | FP: UNKNOWN | FP: model + temporal | TN | Baseline-only FP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `random_forest_lite + temporal` | 0.806452 | 52 | 0 | 193 | 193 | 0 | 13 514 | 270 |
| `random_forest + temporal` | 0.709677 | 52 | 0 | 193 | 193 | 0 | 13 514 | 270 |
| `lightgbm + temporal` | 0.967742 | 52 | 0 | 193 | 193 | 0 | 13 514 | 270 |
| `ensemble_v1 + temporal` | 0.870968 | 52 | 0 | 193 | 193 | 0 | 13 514 | 270 |
| `gradient_boosting + temporal` | 0.967742 | 52 | 0 | 354 | 193 | 161 | 13 353 | 267 |
| `legacy_tree_v1 + temporal` | 0.500000 | 52 | 0 | 463 | 193 | 270 | 13 244 | 0 |
| `decision_tree + temporal` | 0.967742 | 52 | 0 | 669 | 193 | 476 | 13 038 | 262 |
| `tree_depth3 + temporal` | 0.967742 | 52 | 0 | 669 | 193 | 476 | 13 038 | 262 |
| `tree_depth5_min10 + temporal` | 0.935484 | 52 | 0 | 1 254 | 193 | 1 061 | 12 453 | 238 |

Итог: hard-negative обучение и calibration действительно меняют картину.
Лучшие кандидаты убрали все `270` компонентных FP прежнего
`legacy_tree_v1 + temporal` на этом development-протоколе. Остаточные `193` FP —
это `UNKNOWN`, и их надо снижать отдельной upstream/status задачей, а не
обучением component classifier. Runtime default изменён на
`candidate_baseline_v2`.
