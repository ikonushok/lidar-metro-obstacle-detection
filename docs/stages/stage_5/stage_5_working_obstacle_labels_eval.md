# Stage 5: working obstacle labels and event evaluator

Дата: 2026-09-25. Режим: `patch/evaluation`.

## Задача

- Goal: зафиксировать новую рабочую разметку для `doubleT_obstacle` и `cloud_with_fake_obj`, затем дать воспроизводимый event-level evaluator.
- Принятая формулировка: `cloud_with_fake_obj` содержит 10 synthetic objects, подтверждённых организаторами; для задачи проекта target-positive считаются объекты внутри принятого core-габарита поезда.
- Рабочий positive-набор: `doubleT_obstacle` — 1 событие; `cloud_with_fake_obj` — 7 organizer-confirmed target positive obstacles.
- Boundary/negative в `cloud_with_fake_obj`: 3 объекта вне/сверху габарита, их не надо детектить как obstacle.
- Non-goals: не менять runtime detector, геометрию, thresholds, temporal policy, model weights, ROS interfaces или safety decision.
- Allowed files: `docs/stages/stage_5/cloud_with_fake_obj_working_labels.json`, `scripts/evaluate_working_obstacle_labels.py`, этот отчёт, output в `artefacts/stage_5/working_obstacle_labels_eval_20260925/`.
- Защищённые контракты: `UNKNOWN != CLEAR`; event labels не являются runtime safety decision; synthetic held-out используется как development benchmark после раскрытия организаторами состава.
- Primary agent: `agents/lidar_obstacle_pipeline.md`.
- Validation reviewer: применён как проверка уровня claim для evaluator/результатов.
- Target validation: L0 для статического контракта labels/evaluator; L1 после smoke/eval на сохранённых JSON-артефактах.

## Рабочие labels

Машинно-читаемый файл: `docs/stages/stage_5/cloud_with_fake_obj_working_labels.json`.

Сводка:

| Source | Positive target events | Boundary/negative events | Локализовано для frame-window scoring |
|---|---:|---:|---:|
| `doubleT_obstacle` | 1 | 0 | 1 / 1 |
| `cloud_with_fake_obj` | 7 | 3 | 6 / 10 |

`cloud_with_fake_obj` positives:

| № | Event id | Статус |
|---:|---|---|
| 1 | `cloud_fake_obj_01_2x2_center` | positive, localized `204..216` |
| 2 | `cloud_fake_obj_02_small_center` | positive, localized `365..368` |
| 3 | `cloud_fake_obj_03_small_on_rails` | positive, localized `478..480` |
| 4 | `cloud_fake_obj_04_small_edge_inside` | positive, localized `530..532` |
| 6 | `cloud_fake_obj_06_2x2_edge_inside` | positive, localized `579..581` |
| 9 | `cloud_fake_obj_09_long_low_on_rails` | positive, localized `1138..1156` |
| 10 | `cloud_fake_obj_10_narrow_hanging` | positive, needs localization |

Boundary/negative:

| № | Event id | Статус |
|---:|---|---|
| 5 | `cloud_fake_obj_05_small_outside_close` | negative boundary, needs localization |
| 7 | `cloud_fake_obj_07_2x2_outside` | negative boundary, localized `630..633` |
| 8 | `cloud_fake_obj_08_2x2_above` | negative boundary, needs localization |

## Evaluator

Скрипт: `scripts/evaluate_working_obstacle_labels.py`.

Правило:

- positive event hit: есть хотя бы один alarm-frame внутри локализованного event window;
- positive event miss: нет alarm-frame внутри локализованного event window;
- boundary/negative false positive: есть alarm-frame внутри negative event window;
- события с `frame_interval=null` входят в totals, но не входят в localized hit/miss до привязки к кадрам.

Поддерживаемые входы:

- detector frames JSON, например `frames_compact.json`, через поля `causal_temporal_alarm` и `frame_model_alarm`;
- raw CORE components JSON, например `components.json`, через порог `--component-threshold`.

## Отчёт о запуске

Команды:

```powershell
python scripts/evaluate_working_obstacle_labels.py --labels docs/stages/stage_5/cloud_with_fake_obj_working_labels.json --source-id cloud_with_fake_obj --frames artefacts/stage_5/cloud_with_fake_obj_current_detection_20260925/frames_compact.json --output artefacts/stage_5/working_obstacle_labels_eval_20260925/cloud_current_detector.json
```

```powershell
python scripts/evaluate_working_obstacle_labels.py --labels docs/stages/stage_5/cloud_with_fake_obj_working_labels.json --source-id cloud_with_fake_obj --components artefacts/stage_5/cloud_with_fake_obj_raw_core_60m_20260925/components.json --component-threshold 22 --component-threshold 500 --component-threshold 1000 --component-threshold 2000 --output artefacts/stage_5/working_obstacle_labels_eval_20260925/cloud_raw_core_components.json
```

Ожидаемый смысл результата:

- текущий public temporal detector должен быть оценён по `causal_temporal_alarm`;
- per-frame model output остаётся диагностикой, не public detection;
- raw CORE показывает recall upper-bound и boundary/noise risk, не финальное качество.

Фактические артефакты:

- `artefacts/stage_5/working_obstacle_labels_eval_20260925/cloud_current_detector.json`
- `artefacts/stage_5/working_obstacle_labels_eval_20260925/cloud_raw_core_components.json`

Итог по `cloud_with_fake_obj`:

| Detector series | Positive target events | Localized hit / missed | Unlocalized positive | Boundary FP | Alarm frames | Unassigned alarm frames |
|---|---:|---:|---:|---:|---:|---:|
| `causal_temporal_alarm` | 7 | 0 / 6 | 1 | 0 / 1 localized boundary | 0 | 0 |
| `frame_model_alarm` | 7 | 0 / 6 | 1 | 0 / 1 localized boundary | 1 | 1 (`1030`) |
| `raw_core_component_ge_22` | 7 | 6 / 0 | 1 | 1 / 1 localized boundary | 1494 | 1445 |
| `raw_core_component_ge_500` | 7 | 6 / 0 | 1 | 1 / 1 localized boundary | 151 | 112 |
| `raw_core_component_ge_1000` | 7 | 6 / 0 | 1 | 1 / 1 localized boundary | 30 | 1 |
| `raw_core_component_ge_2000` | 7 | 2 / 4 | 1 | 1 / 1 localized boundary | 7 | 0 |

Вывод:

- Текущий public temporal path не детектирует ни один из 6 уже локализованных target-positive объектов `cloud_with_fake_obj`.
- Единственный per-frame model alarm на кадре `1030` не попадает ни в одно локализованное positive/boundary окно и пока считается unassigned diagnostic.
- Raw CORE показывает, что геометрический сигнал для 6 локализованных positives есть уже при порогах `>=22`, `>=500` и `>=1000`, но одновременно поднимает boundary-object #7 (`2x2` outside) как ложную core-positive помеху. Это главный следующий риск для геометрического detector-а.

## Validation

- Achieved level: L1 для нового offline evaluator на сохранённых JSON-артефактах `cloud_with_fake_obj`.
- Проверено: скрипт запускается в Docker image `lidar-mosmetro3d:stage-4-cpu-viewer-v2-best`; outputs созданы и прочитаны.
- Не проверено: full ROS2 replay, визуальная локализация object #10, localization boundary objects #5/#8, перенос evaluator-а на будущий classifier output.

## Остаточный риск

- `cloud_fake_obj_10_narrow_hanging` принят как target-positive по формулировке постановщиков, но пока не привязан к frame interval.
- Boundary objects #5 и #8 тоже требуют localization для автоматического FP-check.
- Без box-level GT evaluator проверяет event windows, а не точную геометрию объекта.
