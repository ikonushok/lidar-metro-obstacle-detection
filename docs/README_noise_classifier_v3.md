# Фильтр препятствий и модели шума, v3

Дата: 2026-09-25.

Этот документ фиксирует статус после проверки единого офлайн-кандидата на
8 источниках, включая новый `cloud_with_fake_obj`, и нашем отборе на собственном
синтетическом наборе.

Предыдущий документ: `docs/README_noise_classifier_v2.md`.

## Единая логика

Имя текущего единого offline-кандидата: `baseline_v3`.

`baseline_v3` =
геометрия сначала проверяет физическое попадание объекта в габарит поезда;
если объект явно внутри габарита -> помеха;
если явно вне/выше габарита -> не помеха;
если случай слабый/маленький/неочевидный -> подключается `model_v1_temporal`.

Подробно:

1. Сначала смотрим: объект физически попадает в габарит поезда или нет.
2. Если попадает в габарит: считаем это помехой.
3. Если объект снаружи габарита или выше поезда: не считаем это помехой.
4. Если объект маленький/слабый и геометрия не даёт уверенного ответа: подключаем `model_v1_temporal` как дополнительную проверку.
5. Если `model_v1_temporal` подтверждает: считаем помехой.
6. Если `model_v1_temporal` не подтверждает: фиксируем `UNKNOWN` и отправляем случай на дополнительную проверку.

Это офлайн-отбор. ROS2/C++-исполнение не менялось.

## Покрытие датасетов

| Датасет или набор | Что проверено в v3 | TP | FN | FP | TN | UNKNOWN | Примечание |
|---|---|---:|---:|---:|---:|---:|---|
| `doubleT_obstacle` | `baseline_v3`, сохранённая ветка `model_v1_temporal_assist` | 52 | 0 | 0 | 149 | 0 | известная помеха `13..64`; событийно 1 TP |
| `cloud_with_fake_obj` | `baseline_v3`, geometry-first event eval | 6 | 0 | 0 | 2 | - | #7/#8 считаются отрицательными boundary-событиями |
| `doubleT_platform` | `baseline_v3`, geometry OR `model_v1_temporal` | 0 | 0 | 0 | 345 | 0 | отрицательный источник |
| `new_data` | `baseline_v3`, geometry OR `model_v1_temporal` | 0 | 0 | 114 | 11128 | 29 | отрицательный источник |
| `roundT_doubleT` | `baseline_v3`, geometry OR `model_v1_temporal` | 0 | 0 | 20 | 232 | 0 | отрицательный источник |
| `roundT_pressureGate_roundT` | `baseline_v3`, geometry OR `model_v1_temporal` | 0 | 0 | 3 | 265 | 0 | отрицательный источник |
| `roundT_squareT_pressureGate_squareT` | `baseline_v3`, geometry OR `model_v1_temporal` | 0 | 0 | 9 | 536 | 0 | отрицательный источник |
| `squareT_platform_squareT_switch` | `baseline_v3`, geometry OR `model_v1_temporal` | 0 | 0 | 3 | 862 | 12 | отрицательный источник |
| `synthetic_obstacles` / `no100_causal_real_synthetic_v1_20260925` | `baseline_v3`, training/screening | 52 | 0 | 93 | 7614 | 23 | не независимый контрольный набор |

Важно: в общей сводке теперь 8 источников: семь старых источников плюс
`cloud_with_fake_obj`. Для `cloud_with_fake_obj` проверена geometry-first
ветка по working labels. Для старых отрицательных источников посчитан
matching union `geometry_gate_ml_suppressor_obstacle OR model_v1_temporal`
из тех же сохранённых geometry-аудит артефактов.
На собственном синтетическом наборе зафиксирован отбор кандидатов, а не
независимая контрольная проверка.

## Оценка единого кандидата по размеченным событиям

Артефакты:

- `artefacts/stage_5/unified_offline_candidate_20260925/`
- `artefacts/stage_5/unified_offline_candidate_20260925/multisource_regression_summary.json`

| Источник | Результат |
|---|---|
| `doubleT_obstacle` | 1 событие TP, 0 FN; 52 TP-кадра `13..64` |
| `cloud_with_fake_obj` | 6 TP, 0 FN по оцениваемым целевым положительным событиям |
| `cloud_with_fake_obj` внешние/верхние объекты | 0 FP на #7/#8; 2 boundary-события корректно не стали помехой |

Текущая оцениваемая разметка `cloud_with_fake_obj`:

- положительные события: #1, #2, #3, #4, #6, #9;
- внешние/верхние отрицательные случаи: #7, #8;
- пока не локализованы или не оцениваются: #5, #10.

#10 пока не оценивается: полное сканирование облака в кадрах `1157..1509` не
подтвердило центральный CORE-positive свисающий объект.

## Сводка по 8 источникам

Это единая offline-сводка `baseline_v3` из сохранённых артефактов. Она не
меняет ROS2/C++ runtime.

Источники чисел:

- итоговая 8-source сводка union:
  `artefacts/stage_5/unified_offline_candidate_20260925/baseline_v3_8source_union_summary.json`;
- старые отрицательные источники, matching union:
  `artefacts/stage_5/baseline_v3_geometry_old_sources_20260925/baseline_v3_union_old_negative_summary.json`;
- `cloud_with_fake_obj`:
  `artefacts/stage_5/unified_offline_candidate_20260925/cloud_with_fake_obj_eval.json`;
- `doubleT_obstacle`:
  `artefacts/stage_5/unified_offline_candidate_20260925/doubleT_obstacle_eval.json`.

| Источник | Проверка | TP | FN | FP | TN | UNKNOWN | Примечание |
|---|---|---:|---:|---:|---:|---:|---|
| `doubleT_obstacle` | `baseline_v3` | 52 | 0 | 0 | 149 | 0 | старая известная помеха, кадры `13..64` |
| `doubleT_platform` | `baseline_v3` | 0 | 0 | 0 | 345 | 0 | отрицательный источник |
| `new_data` | `baseline_v3` | 0 | 0 | 114 | 11128 | 29 | отрицательный источник |
| `roundT_doubleT` | `baseline_v3` | 0 | 0 | 20 | 232 | 0 | отрицательный источник |
| `roundT_pressureGate_roundT` | `baseline_v3` | 0 | 0 | 3 | 265 | 0 | отрицательный источник |
| `roundT_squareT_pressureGate_squareT` | `baseline_v3` | 0 | 0 | 9 | 536 | 0 | отрицательный источник |
| `squareT_platform_squareT_switch` | `baseline_v3` | 0 | 0 | 3 | 862 | 12 | отрицательный источник |
| `cloud_with_fake_obj` | `baseline_v3` | 6 | 0 | 0 | 2 | - | 6 оцениваемых TP; #7/#8 не считаются помехой |

Интерпретация:

- `baseline_v3` сохраняет известную помеху `doubleT_obstacle`;
- `baseline_v3` ловит `cloud_with_fake_obj` по текущей оцениваемой разметке;
- на старых отрицательных источниках matching union даёт `149` FP и `41`
  UNKNOWN против исторического temporal-компаратора `270` FP и `193` UNKNOWN;
- локальный регресс есть на `roundT_pressureGate_roundT`: `3` FP в кадрах
  `110`, `112`, `113` при `0` FP у исторической temporal-ветки;
- суммарная 8-source строка: TP `58`, FN `0`, FP `149`, TN `13519`,
  UNKNOWN `41`. `UNKNOWN` не смешивается с FP и не считается `CLEAR`.

## Проверка старых отрицательных источников

Артефакты:

- `artefacts/stage_5/baseline_v3_geometry_old_sources_20260925/raw_core_60m/`
- `artefacts/stage_5/baseline_v3_geometry_old_sources_20260925/gate_ml_apply/`
- `artefacts/stage_5/baseline_v3_geometry_old_sources_20260925/geometry_old_negative_summary.json`
- `artefacts/stage_5/baseline_v3_geometry_old_sources_20260925/baseline_v3_union_old_negative_summary.json`
- `artefacts/stage_5/roundT_pressureGate_fp_inspection_20260927/roundT_pressureGate_fp_inspection_summary.json`
- `artefacts/stage_5/roundT_pressureGate_fp_inspection_20260927/roundT_pressureGate_fp_component_extents.png`

| Источник | Кадры | FP old temporal | UNKNOWN old | FP geometry | FP model_v1 temporal | FP baseline_v3 union | TN baseline_v3 | UNKNOWN baseline_v3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `doubleT_platform` | 345 | 0 | 0 | 0 | 0 | 0 | 345 | 0 |
| `new_data` | 11271 | 215 | 154 | 47 | 69 | 114 | 11128 | 29 |
| `roundT_doubleT` | 252 | 35 | 10 | 0 | 20 | 20 | 232 | 0 |
| `roundT_pressureGate_roundT` | 268 | 0 | 5 | 3 | 0 | 3 | 265 | 0 |
| `roundT_squareT_pressureGate_squareT` | 545 | 13 | 12 | 0 | 9 | 9 | 536 | 0 |
| `squareT_platform_squareT_switch` | 877 | 7 | 12 | 0 | 3 | 3 | 862 | 12 |
| **Итого** | 13558 | 270 | 193 | 50 | 101 | 149 | 13368 | 41 |

Интерпретация: raw CORE сам по себе очень шумный, но
`geometry_gate_ml_suppressor_obstacle` и causal `model_v1_temporal` вместе
уменьшают суммарный FP/UNKNOWN на старых отрицательных источниках. Единственный
новый локальный провал — три кадра `roundT_pressureGate_roundT` (`110`, `112`,
`113`). Visual/geometric inspection подтвердил, что это не срабатывание
`model_v1_temporal`, а strong geometry gate на длинных низких CORE-компонентах
справа от центра: `1048..1151` точек, `s=3.0..17.4 м`, высота
`0.29..0.31 м`, отношение `extent_y/extent_x` примерно `42..49`. Это похоже
на стационарную инфраструктуру или рельсово-линейный элемент внутри текущего
CORE-гейта.

## Проверка suppressor-а для длинных низких компонентов

Артефакт:

`artefacts/stage_5/long_low_infrastructure_suppressor_screen_20260927/long_low_infrastructure_suppressor_screen.json`

Проверенный offline suppressor подавляет только сильные геометрические
компоненты с большой продольной вытянутостью, малой высотой и боковым смещением.
Результат проверки: `REJECTED_BREAKS_POSITIVE_EVIDENCE`.

| Проверка | До | После | Вывод |
|---|---:|---:|---|
| FP geometry на старых отрицательных источниках | 50 | 7 | улучшает negative screening |
| `roundT_pressureGate_roundT` FP `110/112/113` | 3 | 0 | убирает локальный провал |
| `cloud_with_fake_obj` positive events hit | 6 | 5 | ломает событие #9 |

Причина отказа: `cloud_with_fake_obj` #9 (`long_low_on_rails`) имеет почти те
же признаки, что и локальный FP: длинный низкий боковой CORE-компонент. Простое
подавление таких компонентов снижает FP, но нарушает требование сохранять
оцениваемые положительные события. Поэтому `baseline_v3` остаётся без этого
suppressor-а.

## Отбор no100 на собственном синтетическом наборе

Сохранённый артефакт:

`artefacts/stage_5/no100_causal_real_synthetic_v1_20260925/compact_summary.json`

Итоговая строка `baseline_v3`:

`artefacts/stage_5/unified_offline_candidate_20260925/no100_baseline_v3_summary.json`

Этот прогон включает строки обучения на синтетических данных:

- положительные синтетические компоненты: `925`;
- отрицательные синтетические компоненты: `117,168`;
- всего объединённых строк: `119,320`.

Сводка кандидатов:

| Кандидат | TP | FN | FP всего | FP в `UNKNOWN` | FP временной модели | TN | Статус |
|---|---:|---:|---:|---:|---:|---:|---|
| `baseline_v3` | 52 | 0 | 93 | 23 | 70 | 7614 | прогнан; training/screening |
| `candidate_baseline_v2` | 51 | 1 | 23 | 23 | 0 | 7684 | прогнан |
| `ensemble_v1` | 52 | 0 | 35 | 23 | 12 | 7672 | прогнан |
| `random_forest` | 52 | 0 | 42 | 23 | 19 | 7665 | прогнан |
| `random_forest_lite` | 52 | 0 | 143 | 23 | 120 | 7564 | прогнан |

Это свидетельство обучения и отбора на собственном синтетическом наборе, а не
независимая контрольная валидация. Оно показывает, что синтетическое расширение
данных само по себе не даёт готовый финальный кандидат для ROS2/C++-исполнения:
`candidate_baseline_v2` имеет меньше FP всего, но пропускает один положительный
кадр, а `ensemble_v1`/`random_forest` сохраняют TP 52 и FN 0 с большим FP.

## Вывод

Текущая корректная формулировка:

```text
baseline_v3 можно считать основным offline-кандидатом для следующего
проектного шага: он сохраняет doubleT_obstacle и проходит cloud_with_fake_obj
по оцениваемым событиям без FP на #7/#8.
```

Но это ещё не полноценная замена ROS2/C++-исполнения:

- ROS2/C++-исполнение не менялось;
- геометрическая часть проверена на уровне событий на `cloud_with_fake_obj` и
  отдельным full-frame прогоном на старых отрицательных источниках;
- matching union geometry-first и `model_v1_temporal` для старых отрицательных
  источников пересчитан из сохранённых geometry-аудит артефактов;
- `baseline_v3` сохраняет известный `doubleT_obstacle`, но имеет остаточные
  FP на части отрицательных источников: всего `149`, из них визуально
  подтверждённый локальный geometry-first провал — `roundT_pressureGate_roundT`
  кадры `110`, `112`, `113`;
- свидетельство по собственному синтетическому набору остаётся отбором для
  разработки и обучения, а не независимым доказательством.

## Следующие проверки перед проектированием исполнения

1. Не добавлять простой long-low suppressor в `baseline_v3`: текущий screen
   ломает `cloud_with_fake_obj` #9.
2. Проверить `baseline_v3` на независимом positive/control bag, потому что
   `cloud_with_fake_obj` и no100 остаются development/screening evidence.
3. Если независимый контроль подтвердит проблему FP, проектировать более
   богатый boundary/rail-line признак, а не простой suppressor по вытянутости.
4. Только после этого открывать отдельную задачу по составной логике
   ROS2/C++-исполнения.
