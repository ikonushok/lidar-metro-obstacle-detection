# Этап 5: единый офлайн-кандидат

Дата: 2026-09-25.

## Логика

Единый офлайн-кандидат =
геометрия сначала проверяет физическое попадание объекта в габарит поезда;
если объект явно внутри габарита -> помеха;
если явно вне/выше габарита -> не помеха;
если случай слабый/маленький/неочевидный -> подключается `model_v1_temporal`.

Подробное правило:

1. Сначала смотрим: объект физически попадает в габарит поезда или нет.
2. Если попадает в габарит: считаем это помехой.
3. Если объект снаружи габарита или выше поезда: не считаем это помехой.
4. Если объект маленький/слабый и геометрия не даёт уверенного ответа: подключаем `model_v1_temporal` как дополнительную проверку.
5. Если `model_v1_temporal` подтверждает: считаем помехой.
6. Если `model_v1_temporal` не подтверждает: фиксируем `UNKNOWN` и отправляем случай на дополнительную проверку.

Это офлайн-отбор кандидата. ROS2/C++-исполнение не менялось.

## Реализация проверки

Новый вспомогательный скрипт:

- `scripts/build_unified_offline_candidate.py`

Входы:

- геометрическая ветка для `cloud_with_fake_obj`: `artefacts/stage_5/cloud_boundary_visual_confirm_20260925/gate_ml_working_labels_cloud/frames.json`
- текущие модельные/временные кадры для `cloud_with_fake_obj`: `artefacts/stage_5/cloud_with_fake_obj_current_detection_20260925/frames_compact.json`
- свидетельство `model_v1_temporal` для `doubleT_obstacle`: `artefacts/stage_5/noise_model_eval_temporal_2026_09_23/doubleT_obstacle.json`
- разметка: `docs/stages/stage_5/cloud_with_fake_obj_working_labels.json`

Артефакты:

- `artefacts/stage_5/unified_offline_candidate_20260925/summary.json`
- `artefacts/stage_5/unified_offline_candidate_20260925/cloud_with_fake_obj_frames.json`
- `artefacts/stage_5/unified_offline_candidate_20260925/doubleT_obstacle_frames.json`
- `artefacts/stage_5/unified_offline_candidate_20260925/cloud_with_fake_obj_eval.json`
- `artefacts/stage_5/unified_offline_candidate_20260925/doubleT_obstacle_eval.json`

## Результат

Поле детектора:

```text
unified_offline_candidate_obstacle
```

| Источник | TP событий | FN событий | FP по внешним/верхним объектам | Boundary TN | Кадры со срабатыванием | Примечания |
|---|---:|---:|---:|---:|---:|---|
| `cloud_with_fake_obj` | 6 | 0 | 0 | 2 | 26 | #10 остаётся не локализованным/не оценивается |
| `doubleT_obstacle` | 1 | 0 | 0 | 0 | 52 | кадры `13..64` |

Внешние/верхние случаи `cloud_with_fake_obj`:

- #7 снаружи, кадры `630..633`: срабатывания помехи нет.
- #8 сверху, кадры `674..681`: срабатывания помехи нет.

Случаи `cloud_with_fake_obj`, которые пока не оцениваются:

- #5 снаружи близко: не локализован.
- #10 узкий свисающий: полное сканирование облака не подтвердило центральный CORE-положительный объект; остаётся `frame_interval=null`.

## Ограничение происхождения данных

Для `doubleT_obstacle` покадровый ряд восстановлен из сохранённых метрик `model_v1_temporal`:

```text
52 кадра со срабатыванием
52 TP
0 FN
0 FP
известный положительный интервал 13..64
```

Для этой офлайн-записки этого достаточно, но перед переносом кандидата дальше
нужно отдельной задачей восстановить реальные покадровые строки
`model_v1_temporal` напрямую.

## Решение

Единый офлайн-кандидат проходит текущую оцениваемую цель:

```text
doubleT_obstacle: 1 TP-событие, 0 FN
cloud_with_fake_obj: 6 TP, 0 FN по оцениваемым положительным событиям
cloud #7/#8: 0 ложных срабатываний помехи
```

Перенос в ROS2/C++-исполнение требует отдельной проектной задачи: в ней нужно
описать, как онлайн объединяются геометрия, `model_v1_temporal`, `UNKNOWN` и
решения по объектам снаружи/выше габарита.

## Дополнительная проверка baseline_v3 по 8 источникам и no100

Дата проверки: 2026-09-25.

Задача: зафиксировать `baseline_v3` как имя текущего единого offline-кандидата,
пересобрать сводку по 8 источникам и заполнить строку no100 без смешивания FP и
`UNKNOWN`.

Non-goals:

- не менять ROS2/C++ runtime;
- не менять модели и пороги;
- не делать push или commit.

Изменённые/созданные артефакты:

- `artefacts/stage_5/unified_offline_candidate_20260925/summary.json`;
- `artefacts/stage_5/unified_offline_candidate_20260925/cloud_with_fake_obj_eval.json`;
- `artefacts/stage_5/unified_offline_candidate_20260925/doubleT_obstacle_eval.json`;
- `artefacts/stage_5/unified_offline_candidate_20260925/multisource_regression_summary.json`;
- `artefacts/stage_5/unified_offline_candidate_20260925/no100_baseline_v3_summary.json`;
- `docs/README_noise_classifier_v3.md`.

Фактически выполненные команды:

```powershell
C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile scripts\build_unified_offline_candidate.py scripts\evaluate_working_obstacle_labels.py

C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\build_unified_offline_candidate.py --output-dir artefacts\stage_5\unified_offline_candidate_20260925 --cloud-geometry-frames artefacts\stage_5\cloud_boundary_visual_confirm_20260925\gate_ml_working_labels_cloud\frames.json --cloud-model-frames artefacts\stage_5\cloud_with_fake_obj_current_detection_20260925\frames_compact.json --doublet-temporal-summary artefacts\stage_5\noise_model_eval_temporal_2026_09_23\doubleT_obstacle.json --seven-source-temporal-dir artefacts\stage_5\noise_model_eval_temporal_2026_09_23 --no100-compact-summary artefacts\stage_5\no100_causal_real_synthetic_v1_20260925\compact_summary.json --cloud-eval artefacts\stage_5\unified_offline_candidate_20260925\cloud_with_fake_obj_eval.json --doublet-eval artefacts\stage_5\unified_offline_candidate_20260925\doubleT_obstacle_eval.json

C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\evaluate_working_obstacle_labels.py --labels docs\stages\stage_5\cloud_with_fake_obj_working_labels.json --source-id cloud_with_fake_obj --frames artefacts\stage_5\unified_offline_candidate_20260925\cloud_with_fake_obj_frames.json --detector-field inside_gabarit_by_geometry --detector-field model_v1_temporal_assist --detector-field outside_or_above_by_geometry --detector-field unified_offline_candidate_obstacle --output artefacts\stage_5\unified_offline_candidate_20260925\cloud_with_fake_obj_eval.json

C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\evaluate_working_obstacle_labels.py --labels docs\stages\stage_5\cloud_with_fake_obj_working_labels.json --source-id doubleT_obstacle --frames artefacts\stage_5\unified_offline_candidate_20260925\doubleT_obstacle_frames.json --detector-field inside_gabarit_by_geometry --detector-field model_v1_temporal_assist --detector-field outside_or_above_by_geometry --detector-field unified_offline_candidate_obstacle --output artefacts\stage_5\unified_offline_candidate_20260925\doubleT_obstacle_eval.json
```

Результат:

- `doubleT_obstacle`: событие сохранено, TP 1, FN 0; покадрово TP 52, FN 0, FP 0.
- `cloud_with_fake_obj`: TP 6, FN 0, FP 0 по оцениваемым событиям; #7/#8 не
  считаются помехой.
- Старые отрицательные источники: FP/UNKNOWN не ухудшились относительно
  сохранённых `model_v1_temporal` summaries.
- no100 training/screening: TP 52, FN 0, FP всего 93, FP в `UNKNOWN` 23,
  FP временной модели 70, TN 7614.

Уровень валидации: L1/L3 для offline-артефактов этой проверки. Это не
runtime-доказательство и не independent held-out.

Непроверено:

- полноценная geometry inside/outside покадровая ветка на старых 7 источниках;
- независимый positive/control bag;
- ROS2/C++ интеграция.

Следующий минимальный тест: сгенерировать реальные покадровые строки
`model_v1_temporal` и geometry inside/outside для старых 7 источников, затем
повторить сравнение FP/UNKNOWN без опоры только на summary-метрики.
