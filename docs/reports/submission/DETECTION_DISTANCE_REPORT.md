# Detection Distance Report

Дата: 2026-09-28.

## Цель

Измерить расстояние до первого предупреждения и первого уверенного обнаружения
препятствия на доступных positive windows:

- `doubleT_obstacle`, кадры `13..64`;
- `cloud_with_fake_obj`, пользовательские visible windows из
  `review_object_catalog.visible_frames_inclusive`; для `obj09`, у которого нет
  user-visible записи, используется scoring-only positive window из
  `sources[].positive_events`.

Это не production-дальность и не расстояние от носа поезда. Все расстояния ниже
считаются от source LiDAR origin (`distance_reference=SOURCE_ORIGIN`,
`distance_units=m_ASSUMED`). `80 м` остаётся только горизонтом построения
envelope, а не измеренной дальностью обнаружения.

## Метод

Прогон выполнен через direct C++ runtime, тем же runtime policy:

```text
development_candidate / rail_forward_min_m=2.0 / tangent / baseline_v3
```

Измерялись два момента:

- **предупреждение** — оранжевая UI-надпись плеера: ранний C++ candidate
  держится 3 кадра подряд;
- **public detection** — первый кадр с `intrusion_candidate_present=true`.

В текущем `baseline_v3` трёхкадровый early candidate поднимается в public
`intrusion_candidate_present=true`. Поэтому headless ROS2 JSON, evaluator и
браузерный плеер видят один и тот же ранний результат.

Если предупреждение появляется раньше уверенной детекции, в таблице показаны
оба расстояния и оба номера кадра.

## Команда

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" `
  lidar-metro-obstacle-detection:submission `
  bash -lc "source /opt/ros/humble/setup.bash && source /app/install/setup.bash && python3 /workspace/scripts/measure_detection_distances.py --root /workspace --progress"
```

## Результаты

| Источник | Событие | Окно | Предупреждение | Public detection |
|---|---|---:|---:|---:|
| `doubleT_obstacle` | real obstacle | 13..64 | нет | f14 / 55.580 м |
| `cloud_with_fake_obj` | `obj01`, 2x2 м по центру | 135..228 | f137 / 68.069 м | f137 / 68.069 м |
| `cloud_with_fake_obj` | `obj02`, 0,3x0,3 м по центру | 353..368 | f363 / 13.598 м | f363 / 13.598 м |
| `cloud_with_fake_obj` | `obj03`, 0,3x0,3 м на рельсах | 462..479 | f475 / 10.850 м | f475 / 10.850 м |
| `cloud_with_fake_obj` | `obj04`, 0,3x0,3 м у края габарита | 514..532 | f528 / 9.915 м | f528 / 9.915 м |
| `cloud_with_fake_obj` | `obj06`, 2x2 м у края внутри | 567..581 | нет | f579 / 8.232 м |
| `cloud_with_fake_obj` | `obj09`, 2x0,2 м на рельсах | 1138..1156 | нет | f1138 / 3.332 м |

## Артефакты

- `artefacts/current_model_validation/detection_distance_summary.json`
- `artefacts/current_model_validation/detection_distance_summary.md`

## Вывод

На доступных positive windows `baseline_v3` обнаруживает все 7 проверенных
событий: 1 real development interval, 5 user-visible fake-object windows и 1
scoring-only fake-object window.

Самое дальнее предупреждение в user-visible окнах `cloud_with_fake_obj`:
`obj01`, f137 / `68.069 м`. Скрин с f142 / `65.7 м` — более поздний кадр того
же предупреждения.

Самая дальняя первая уверенная детекция в этом срезе — `55.580 м` на
`doubleT_obstacle`. На `cloud_with_fake_obj` самая дальняя первая public
детекция — `68.069 м` для `obj01`.

Для `obj01`, `obj02`, `obj03` и `obj04` public detection совпадает с
трёхкадровым early warning. Для `doubleT_obstacle`, `obj06` и `obj09`
отдельного раннего UI-предупреждения до public detection не зафиксировано.

## Уровень валидации

L1/L3 для доступных development/screening positive windows. Не является
независимым hidden-test результатом, production safety evidence или измеренной
дальностью от носа поезда.
