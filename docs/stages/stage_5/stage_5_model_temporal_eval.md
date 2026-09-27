# Stage 5: model_v1 temporal evaluator column

## Цель

Добавить в offline evaluator отдельную метрику `model_v1 + temporal`, чтобы оценить эффект post-model temporal filter по тем же записям, где уже сравниваются `legacy` и `model_v1`.

## Non-goals

- Не менять C++ backend decision.
- Не переобучать `model_v1`.
- Не заявлять независимый recall: `doubleT_obstacle` остаётся обучающим положительным проездом.

## Контракт

`UNKNOWN` не считается чистым кадром. `model_v1` остаётся базовой покадровой колонкой. Новая колонка считается отдельно как frame-level `2-of-3`: текущий кадр имеет `model_alarm=True` и хотя бы один соседний кадр тоже имеет `model_alarm=True`.

## Проверка

- Unit test evaluator temporal summarization.
- Spot-check replay по `doubleT_obstacle`, `roundT_doubleT`, `roundT_squareT_pressureGate_squareT`.
- Full 7-source replay выполнен в `artefacts/stage_5/noise_model_eval_temporal_2026_09_23`.

## Результат

| Scope | `model_v1` FP | `model_v1 + temporal` FP | Изменение |
|---|---:|---:|---:|
| 7 записей, условная разметка README | 457 | 270 | -187 |

`doubleT_obstacle` остался 52/52 TP и 0 FP. `new_data` улучшился с 374 до 215 FP-кадров. Новая метрика добавлена в `docs/README_noise_classifier.md` как диагностическая post-model колонка, не заменяющая baseline `model_v1`.

## Риски

Frame-level temporal может подтвердить соседние разные компоненты; это диагностическая метрика, а не окончательный runtime safety contract. Component-level matching можно добавить отдельным шагом.
