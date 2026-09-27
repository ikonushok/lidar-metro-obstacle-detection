# Фильтр препятствий и модели шума, v2

Дата: 2026-09-24.

Этот документ обновляет результат `docs/README_noise_classifier.md` после
upstream/status правки для `UNKNOWN` причины
`AMBIGUOUS_LOCAL_CONTINUITY_PATH`. Старый документ оставлен как baseline для
сравнения.

## Проверка конфликта с обучением

Перед прогоном проверено, что эта работа не конфликтует с процессом
«Обучить и сравнить классификатор»:

- запуск выполнялся через `scripts/evaluate_noise_model_candidates.py`;
- runtime-модель `models/noise_classifier_candidate_baseline_v2.json` не
  изменялась;
- C++ export `src/cpp/candidate_baseline_v2_model.inc` не регенерировался;
- флаг `--export-candidate-output` не использовался;
- новые обученные кандидаты сохранены только в
  `artefacts/stage_5/noise_model_candidate_shared_station_fix_v2_all_sources/trained_models/`;
- синтетика не использовалась.

Следовательно, v2-числа ниже — это offline-сравнение кандидатов после
upstream/status фикса, а не молчаливая замена runtime ML-модели.

## Что изменилось перед v2

В `DetectAutoRails` исправлена причина ложной неоднозначности: конкурирующие
локально непрерывные цепочки теперь сравниваются по боковому расхождению на
общих `source_s_m` station. Если общих station нет, остаётся прежний endpoint
fallback. Это не превращает `UNKNOWN` в `CLEAR`: часть кадров получает
поддержанную ось и затем обычный downstream статус, а настоящая неоднозначность
остаётся `UNKNOWN`.

Подробный аудит и smoke/full evidence:
`docs/stages/stage_5/stage_5_unknown_status_audit.md`.

## Новый полный прогон

Команда:

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/workspace" -w /workspace -e PYTHONPATH=/workspace/scripts:/workspace/src lidar-mosmetro3d:unknown-axis-shared-station-fix python3 scripts/evaluate_noise_model_candidates.py --root /workspace --output /workspace/artefacts/stage_5/noise_model_candidate_shared_station_fix_v2_all_sources --stream-cli /app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli --stream-mode 2.0 --temporal-mode legacy_adjacent --training-mode hard_negative --hard-negative-source doubleT_platform --hard-negative-source new_data --hard-negative-source roundT_doubleT --hard-negative-source roundT_pressureGate_roundT --hard-negative-source roundT_squareT_pressureGate_squareT --hard-negative-source squareT_platform_squareT_switch --regular-negative-ratio 20 --calibrate-thresholds --calibration-source doubleT_obstacle --calibration-source roundT_doubleT --threshold-steps 31
```

Артефакт:
`artefacts/stage_5/noise_model_candidate_shared_station_fix_v2_all_sources/noise_model_candidates.json`.

Scope:

- seven-source development run, `13,759` кадров;
- temporal metric mode: `legacy_adjacent` — offline diagnostic rule from this
  v2 table: current alarm plus previous or next adjacent alarm in the same
  source. Do not silently compare this table to `causal_runtime` artifacts;
  that mode answers a different question and currently chooses different
  thresholds.
- positive только `doubleT_obstacle:13-64`;
- все остальные кадры считаются negative по текущему рабочему допущению;
- `UNKNOWN` считается FP для negative кадров;
- `UNKNOWN_FP` и `model_temporal_FP` показаны отдельно.

Training summary:

- `52` positive components;
- `288` hard-negative components;
- `1040` regular-negative components;
- всего `1380` training components.

## Итог v2 по всем моделям

`Raw FP` — это ложные срабатывания до temporal-фильтра.

`Threshold` — это порог срабатывания модели. Модель для каждого компонента
выдаёт score: насколько компонент похож на препятствие. Потом score
сравнивается с порогом:

- score >= `Threshold` → считать компонент тревожным;
- score < `Threshold` → считать компонент шумом / не тревогой.

Пример: `random_forest_lite`, threshold `0.806452`. Значит компонент становится
alarm-кандидатом только если модель дала score примерно `0.806` или выше. В
таблице разные модели имеют разные `Threshold`, потому что порог подбирался на
calibration-срезе, чтобы сохранить `TP=52, FN=0` и снизить FP.

| Модель | Threshold | TP | FN | UNKNOWN_FP | model_temporal_FP | FP_total | TN | Raw FP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `random_forest_lite + temporal` | 0.838710 | 52 | 0 | 41 | 0 | 41 | 13,666 | 50 |
| `random_forest + temporal` | 0.774194 | 52 | 0 | 41 | 0 | 41 | 13,666 | 43 |
| `ensemble_v1 + temporal` | 0.903226 | 52 | 0 | 41 | 0 | 41 | 13,666 | 43 |
| `lightgbm + temporal` | 0.967742 | 52 | 0 | 41 | 91 | 132 | 13,575 | 350 |
| `legacy_tree_v1 + temporal` | 0.500000 | 52 | 0 | 41 | 277 | 318 | 13,389 | 505 |
| `gradient_boosting + temporal` | 0.967742 | 52 | 0 | 41 | 979 | 1,020 | 12,687 | 1,974 |
| `decision_tree + temporal` | 0.967742 | 52 | 0 | 41 | 1,066 | 1,107 | 12,600 | 2,073 |
| `tree_depth3 + temporal` | 0.967742 | 52 | 0 | 41 | 1,066 | 1,107 | 12,600 | 2,073 |
| `tree_depth5_min10 + temporal` | 0.967742 | 52 | 0 | 41 | 1,127 | 1,168 | 12,539 | 2,143 |

## Итог v2 по лучшей модели: random_forest_lite + temporal

Метрики ниже считаются после temporal-фильтра. `FP` включает `UNKNOWN`,
потому что для пользователя это ложная/неполезная тревога, а не `CLEAR`.

| Датасет | TP | TN | FP | FN |
|---|---:|---:|---:|---:|
| `doubleT_obstacle` | 52 | 149 | 0 | 0 |
| `doubleT_platform` | 0 | 345 | 0 | 0 |
| `new_data` | 0 | 11,242 | 29 | 0 |
| `roundT_doubleT` | 0 | 252 | 0 | 0 |
| `roundT_pressureGate_roundT` | 0 | 268 | 0 | 0 |
| `roundT_squareT_pressureGate_squareT` | 0 | 545 | 0 | 0 |
| `squareT_platform_squareT_switch` | 0 | 865 | 12 | 0 |
| **Итого** | **52** | **13,666** | **41** | **0** |

Для лучших трёх моделей:

- `TP/FN` на `doubleT_obstacle`: `52 / 0`;
- `UNKNOWN_FP`: `41`;
- `model_temporal_FP`: `0`;
- `FP_total`: `41`.

Оставшиеся `UNKNOWN_FP` причины одинаковы для всех кандидатов:

| Причина | Reason code | Кадров |
|---|---|---:|
| Неоднозначная непрерывная цепочка рельсовой оси | `AMBIGUOUS_LOCAL_CONTINUITY_PATH` | 33 |
| Недостаточное непрерывное покрытие опорных сечений | `INSUFFICIENT_CONTIGUOUS_COVERAGE` | 4 |
| Недостаточно локально непрерывных пар рельсов | `INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT` | 4 |

## Сравнение с README_noise_classifier.md

Старый документ использует артефакт
`artefacts/stage_5/noise_model_candidate_hard_negative_all_sources_cal_roundT/noise_model_candidates.json`.
Новый v2 использует артефакт
`artefacts/stage_5/noise_model_candidate_shared_station_fix_v2_all_sources/noise_model_candidates.json`.

| Модель | FP_total old | UNKNOWN_FP old | model_temporal_FP old | FP_total v2 | UNKNOWN_FP v2 | model_temporal_FP v2 | Δ FP_total |
|---|---:|---:|---:|---:|---:|---:|---:|
| `random_forest_lite + temporal` | 193 | 193 | 0 | 41 | 41 | 0 | -152 |
| `random_forest + temporal` | 193 | 193 | 0 | 41 | 41 | 0 | -152 |
| `ensemble_v1 + temporal` | 193 | 193 | 0 | 41 | 41 | 0 | -152 |
| `lightgbm + temporal` | 193 | 193 | 0 | 132 | 41 | 91 | -61 |
| `legacy_tree_v1 + temporal` | 463 | 193 | 270 | 318 | 41 | 277 | -145 |
| `gradient_boosting + temporal` | 354 | 193 | 161 | 1,020 | 41 | 979 | +666 |
| `decision_tree + temporal` | 669 | 193 | 476 | 1,107 | 41 | 1,066 | +438 |
| `tree_depth3 + temporal` | 669 | 193 | 476 | 1,107 | 41 | 1,066 | +438 |
| `tree_depth5_min10 + temporal` | 1,254 | 193 | 1,061 | 1,168 | 41 | 1,127 | -86 |

Изменение по upstream/status:

- `UNKNOWN_FP`: `193 -> 41`, то есть `-152`;
- оставшиеся `41` — всё ещё `MISSING_CURVE_AXIS`, не ML-компонентные ошибки;
- лучшие модели сохраняют `model_temporal_FP=0`.

Изменение по recall:

- old: `TP=52`, `FN=0`;
- v2: `TP=52`, `FN=0`;
- ухудшения на известном `doubleT_obstacle` нет.

## Вывод

Главный эффект v2 — не новая ML-модель, а upstream/status исправление выбора
рельсовой оси. Оно снимает 152 ложных `UNKNOWN` в полном seven-source
development-прогоне и сохраняет `52/0` TP/FN на известном obstacle-интервале.

Практически лучший кандидат остаётся `random_forest_lite`: он делит первое
место по `FP_total=41`, имеет `model_temporal_FP=0`, и остаётся самым удобным
для переносимого C++ runtime. Но текущий runtime export не обновлён этим
документом; если нужно заменить runtime baseline на v2 threshold/model, это
должно идти отдельной задачей через процесс «Обучить и сравнить классификатор».

Ограничение сохраняется: это development-оценка, а не независимый test. Перед
финальным утверждением качества нужны held-out/visual review оставшихся
`41 UNKNOWN_FP` и отдельная runtime-проверка direct/ROS2 пути.
