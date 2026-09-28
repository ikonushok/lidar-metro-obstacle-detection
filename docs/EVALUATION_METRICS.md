# Метрики baseline_v3

Основная таблица для передачи организаторам строится одной командой и содержит
только replay-источники, которые прогоняются через текущий `baseline_v3`.

```powershell
docker build -t lidar-metro-obstacle-detection:submission .
docker run --rm `
  -v "${PWD}:/workspace" `
  lidar-metro-obstacle-detection:submission `
  bash -lc "source /opt/ros/humble/setup.bash && source /app/install/setup.bash && python3 /workspace/scripts/evaluate_baseline_v3_metrics.py --root /workspace"
```

Правила разметки лежат в [`config/evaluation_labels.json`](../config/evaluation_labels.json).

- `real replay sources` считаются покадрово. Для `doubleT_obstacle` положительный
  интервал: кадры `13..64`; остальные real replay кадры считаются negative, если
  для них нет отдельной разметки.
- `cloud_with_fake_obj` включён осторожно: это `working event-window labels`, не
  полный GT от организаторов. Для него считаются события, а не все кадры.
- `UNKNOWN` не считается подтверждённым `CLEAR`. Основная таблица считает
  наличие/отсутствие `intrusion_candidate_present`; диагностические статусы
  runtime надо смотреть отдельно.
- Экспериментальное оранжевое предупреждение плеера в эту таблицу не входит:
  оно появляется после трёх подряд кадров с C++ ранним кандидатом, без
  проверки принадлежности одному объекту, и может сосуществовать с `UNKNOWN`.
  Красное предупреждение и красные точки соответствуют основному
  `intrusion_candidate_present=true`, но не гарантируют реальное препятствие.
  `47` в строке `new_data` — ложноположительные **кадры**, а не 47 независимых
  событий, согласно сообщению пользователя об отсутствии препятствий в записи.
  `6/6` на синтетике — попадание в рабочие окна событий, не подтверждение
  пространственного совпадения красных точек с шестью конкретными объектами.
- `synthetic_no100` не входит в основную таблицу: это наш component-level
  development probe, не внешний replay-bag и не та же единица оценки.

## Хакатонная интерпретация

Для отчёта, презентации и комментариев жюри эту таблицу следует описывать как
воспроизводимый срез `baseline_v3` на доступных replay-источниках, а не как
скрытый test set или production-валидацию. `doubleT_obstacle` остаётся
development-positive сценой, `cloud_with_fake_obj` — screening/working
event-window evidence, а `new_data` используется как длинная negative-запись по
сообщению пользователя об отсутствии препятствий.

Если перед отправкой метрики пересчитываются заново, в материалах сдачи нужно
обновить итоговую таблицу, commit hash и кратко указать команду пересчёта.
Если пересчёт не выполнялся, не заменять приведённые ниже числа вручную.

Итоговые метрики:

```text
dataset                                TP     TN      FP    FN
roundT_doubleT                         0      252     0     0
squareT_platform_squareT_switch         0      877     0     0
doubleT_platform                        0      345     0     0
roundT_squareT_pressureGate_squareT     0      545     0     0
doubleT_obstacle                        51     149     0     1
roundT_pressureGate_roundT              0      265     3     0
new_data                                0      11224   47    0
cloud_with_fake_obj                     6      1       0     0
```

Для длинных проверок можно запускать отдельный источник:

```powershell
docker run --rm `
  -v "${PWD}:/workspace" `
  lidar-metro-obstacle-detection:submission `
  bash -lc "source /opt/ros/humble/setup.bash && source /app/install/setup.bash && python3 /workspace/scripts/evaluate_baseline_v3_metrics.py --root /workspace --source new_data --progress-every 250"
```

Опции `--start` и `--end` предназначены для диагностических частичных прогонов.
Для финальной таблицы источник надо прогонять целиком.
